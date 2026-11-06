# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Access authentication for internal API.

Internal API (``/rest/v1/orchestrate/*``):
    Database-backed user authentication. Users are stored in the PostgreSQL
    or MySQL ``users`` table with versioned bcrypt password hashes. Session tokens
    use shared SQL storage with configurable TTL (file mode remains in-memory).

External API (``/api/v1/*``):
    Account Bearer tokens share identity, TTL and revocation with user sessions.
    Explicit legacy machine authentication is available for direct integrations.
    Cookies alone never authorize the public API.
"""

import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from loguru import logger
from starlette import status
from starlette.responses import JSONResponse, Response

from common.util.config_util import get_conf
from orchestrate.persistence import current_context
from orchestrate.persistence.errors import StorageError
from orchestrate.server.storage_error_response import storage_http_exception
from orchestrate.server.response_utils import ok, error

# Endpoints that must remain public even when auth is enabled.
_PUBLIC_AUTH_PATHS = {
    "/rest/v1/orchestrate/auth/login",
    "/rest/v1/orchestrate/auth/check",
    "/rest/v1/orchestrate/auth/register",
}

# Default token lifetime: 12 hours.
_DEFAULT_TTL = 12 * 60 * 60


@dataclass(frozen=True)
class SessionIdentity:
    username: str
    role: str
    must_change_password: bool = False
    subject_id: str | None = None

# Browser sessions use an httpOnly cookie; public APIs require an explicit
# Bearer header even if a cookie is present. Cookie name intentionally
# differs from the old "?access_token=..." query param name it replaces
# (see extract_token -- that scheme is no longer accepted at all), to make
# the two easy to tell apart in logs/captures from before this migration.
SESSION_COOKIE_NAME = "session_token"
# Path=/ rather than the internal API prefix: the browser scopes cookies to
# the URL it actually requested, which in gateway mode carries the
# /api/orchestrate prefix the proxy (nginx or the Vite dev proxy) strips
# before this backend ever sees the request. A narrower Path here matches
# neither that prefixed shape nor the unprefixed one direct-IP mode uses,
# so the browser would silently never send the cookie back at all -- login
# would appear to succeed while every following request 401s. httpOnly
# already blocks script-level reads, so the narrower scope bought nothing
# a same-origin SPA+API deployment needed anyway.
SESSION_COOKIE_PATH = "/"


def _is_https_enabled() -> bool:
    return str(get_conf().get("enable_https", True)).lower() == "true"


def set_session_cookie(response: Response, token: str, ttl: int, request: Request | None = None) -> None:
    """Attach the session cookie to a response after a successful login.

    Secure follows the explicit public scheme, or the request scheme resolved
    by Uvicorn's trusted-proxy policy. Backend TLS alone does not determine
    the browser-facing transport.
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=_public_https(request),
        samesite="lax",
    )


def _public_https(request: Request | None) -> bool:
    scheme = str(get_conf().get("public_scheme", "")).strip().lower()
    if scheme:
        if scheme not in {"http", "https"}:
            raise ValueError("public_scheme must be http or https")
        return scheme == "https"
    # Uvicorn resolves trusted proxy headers before reaching the application.
    # Do not inspect caller-supplied X-Forwarded-Proto here.
    return request.url.scheme == "https" if request is not None else _is_https_enabled()


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path=SESSION_COOKIE_PATH)


def is_auth_enabled() -> bool:
    """Return True when authentication is enabled.

    In database mode (PostgreSQL/MySQL): checks if the users table has any user. Raises
    RuntimeError when the user store is unreachable -- callers must fail
    closed (503) instead of treating "cannot determine" as "auth disabled".
    In file mode: checks ``access_password`` in server.conf.

    """
    conf = get_conf()
    storage = current_context()
    if storage.has_users:
        # Credentials live in the configured backend, which is what declares
        # the user-store capability. The repository still raises when that
        # store is unreachable, so callers keep failing closed.
        return storage.users.has_any()
    # File mode: config-based auth
    return bool(conf.get("access_password", "").strip())



def _get_ttl() -> int:
    conf = get_conf()
    try:
        ttl = int(conf.get("access_token_ttl", _DEFAULT_TTL))
        return ttl if ttl > 0 else _DEFAULT_TTL
    except (ValueError, TypeError):
        return _DEFAULT_TTL


class _SessionStore:
    """Thread-safe in-memory token store with TTL.

    Single-process only (see #14): a token minted by one worker/replica
    isn't visible to another, and every restart drops all sessions. Fine
    for the single-process launch paths this project ships today; revisit
    with a shared backend (DB/Redis) before ever running multiple workers
    or replicas. See the "Session storage is single-process only" note in
    README.md for the operator-facing version of this.
    """

    def __init__(self):
        # token -> (username, role, expiry epoch)
        self._tokens: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.Lock()
        self._revision = 0
        self._user_revocations: dict[str, int] = {}

    def login_revision(self) -> int:
        """Fence a password check that can run concurrently with account changes."""
        with self._lock:
            return self._revision

    def create(self, username: str, role: str = "user", *, login_revision: int | None = None) -> tuple[str, int]:
        """Create a new session token for the given user and role.

        ``role`` is stamped once at login rather than re-resolved per
        request, so admin-only checks don't add a DB lookup to every
        authenticated request.
        """
        token = secrets.token_urlsafe(32)
        ttl = _get_ttl()
        expiry = time.time() + ttl
        with self._lock:
            if login_revision is not None and self._user_revocations.get(username, 0) > login_revision:
                raise HTTPException(401, "Account changed during login; please log in again")
            self._cleanup_locked()
            self._tokens[token] = (username, role, expiry)
        logger.info(f"Session token created for user '{username}' (role={role}), expires in {ttl}s")
        return token, ttl

    def validate(self, token: str) -> bool:
        """Return True if the token exists and has not expired."""
        if not token:
            return False
        now = time.time()
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None:
                return False
            if now >= entry[2]:
                del self._tokens[token]
                return False
            return True

    def get_username(self, token: str) -> str | None:
        """Return the username associated with the token, or None."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None or now >= entry[2]:
                self._tokens.pop(token, None)
                return None
            return entry[0]

    def get_role(self, token: str) -> str | None:
        """Return the role associated with the token, or None."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None or now >= entry[2]:
                self._tokens.pop(token, None)
                return None
            return entry[1]

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)

    def revoke_user(self, username: str) -> None:
        """Credential changes/deletion invalidate both browser and API tokens."""
        with self._lock:
            self._revision += 1
            self._user_revocations[username] = self._revision
            for token, entry in list(self._tokens.items()):
                if entry[0] == username:
                    del self._tokens[token]

    def identity(self, token: str | None) -> SessionIdentity | None:
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None:
                return None
            if time.time() >= entry[2]:
                del self._tokens[token]
                return None
            return SessionIdentity(entry[0], entry[1])

    def _cleanup_locked(self) -> None:
        """Remove expired tokens (caller must hold the lock)."""
        now = time.time()
        expired = [t for t, (_, _, exp) in self._tokens.items() if now >= exp]
        for t in expired:
            del self._tokens[t]


# Singleton - survives across requests within the same process.
_session_store = _SessionStore()


def get_session_store():
    context = current_context()
    if getattr(context, "mode", None) in {"postgresql", "mysql"}:
        from orchestrate.server.sql_sessions import shared_store
        try:
            return shared_store(context.backend._provider)
        except StorageError as exc:
            raise storage_http_exception(exc) from exc
    return _session_store


def create_account_session(store, user, revision):
    """Bind SQL issuance to the credential snapshot actually verified."""
    from orchestrate.server.sql_sessions import SqlSessionStore
    if isinstance(store, SqlSessionStore):
        return store.create(user["username"], user.get("role", "user"),
                            credential_snapshot=user.get("_auth_snapshot"))
    return store.create(user["username"], user.get("role", "user"), login_revision=revision)


def validate_job_identity(subject_id: str, role: str) -> bool:
    """Shared authority check for durable dispatch; never stores the user's token."""
    from orchestrate.server.sql_sessions import SqlSessionStore
    store = get_session_store()
    if isinstance(store, SqlSessionStore):
        return store.subject_authorized(subject_id, role)
    # File jobs are single-process and use the configured admin identity.
    return subject_id == "admin" and role == "admin" and is_auth_enabled()


def extract_bearer_token(request: Request) -> str | None:
    """One explicit Authorization value; no cookies, query or duplicate fallback."""
    values = request.headers.getlist("authorization")
    parts = values[0].split() if len(values) == 1 else []
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def extract_token(request: Request) -> str | None:
    """Extract an explicit Bearer header, otherwise the browser session cookie.

    No query-param fallback: that was the "?access_token=..." scheme this
    migration replaces, which leaked the token into server access logs,
    browser history, and Referer headers on every SSE call (see #39). The
    frontend no longer sends it; EventSource picks up the cookie instead.
    """
    # Explicit headers take precedence, even malformed ones: do not silently
    # act as the cookie owner when a script supplies another credential.
    if "authorization" in request.headers:
        return extract_bearer_token(request)
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None


def require_user_authentication() -> None:
    try:
        enabled = is_auth_enabled()
    except RuntimeError:
        raise HTTPException(503, "Authentication backend unavailable") from None
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    if not enabled:
        raise HTTPException(503, "Account authentication is not configured")


def require_session_identity(request: Request, *, allow_cookie: bool = True,
                             allow_password_change: bool = False) -> SessionIdentity:
    token = extract_token(request) if allow_cookie else extract_bearer_token(request)
    try:
        identity = get_session_store().identity(token)
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    if identity is None:
        raise HTTPException(401, "Valid login token required", headers={"WWW-Authenticate": "Bearer"})
    if identity.role not in {"admin", "user"}:
        raise HTTPException(403, "Account role is not permitted")
    if (identity.must_change_password
            or username_must_change_password(identity.username)) and not allow_password_change:
        raise HTTPException(403, "Password change required")
    return identity


def require_admin(request: Request) -> None:
    """FastAPI dependency: reject the request unless the session role is 'admin'.

    An unconfigured account backend fails closed, including direct invocation
    of this dependency; middleware is not the sole enforcement boundary.
    """
    try:
        auth_enabled = is_auth_enabled()
    except RuntimeError as e:
        # Fail closed with 503 when the user store is unreachable.
        logger.error(f"[Auth] Authentication backend unavailable: {e}")
        raise HTTPException(status_code=503, detail="Authentication backend unavailable")
    except StorageError as e:
        raise storage_http_exception(e) from e
    if not auth_enabled:
        raise HTTPException(status_code=503, detail="Account authentication is not configured")
    token = extract_token(request)
    identity = get_session_store().identity(token) if token else None
    if identity is not None:
        require_session_identity(request)
    role = identity.role if identity is not None else None
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


# Usernames that must change their password before anything else is allowed.
# Populated at login from the DB (see #12) rather than re-queried per
# request, matching the session-role pattern -- avoids a DB round trip on
# every authenticated request. Self-healing across restarts: the set is
# empty on startup, but the next login for a still-pending user repopulates
# it from the DB's own must_change_password column.
_pending_password_change: set[str] = set()
_pending_password_change_lock = threading.Lock()

# Authenticated paths that must stay reachable for a user stuck in the
# forced-change state, or they'd have no way to actually clear it.
_PASSWORD_CHANGE_EXEMPT_PATHS = {
    "/rest/v1/orchestrate/auth/change-password",
    "/rest/v1/orchestrate/auth/logout",
}


def mark_must_change_password(username: str) -> None:
    with _pending_password_change_lock:
        _pending_password_change.add(username)


def clear_must_change_password(username: str) -> None:
    with _pending_password_change_lock:
        _pending_password_change.discard(username)


def username_must_change_password(username: str | None) -> bool:
    if not username:
        return False
    store = get_session_store()
    from orchestrate.server.sql_sessions import SqlSessionStore
    if isinstance(store, SqlSessionStore):
        try:
            return store.requires_password_change(username)
        except StorageError as exc:
            raise storage_http_exception(exc) from exc
    with _pending_password_change_lock:
        return username in _pending_password_change


# Path prefixes that require application-layer token auth. "/psops" is a
# legacy alias registered at the application root (see
# frontend_support_server.py) and exposes the same workflow CRUD/execute
# surface as the internal API -- it must not sit outside the auth gate.
_PROTECTED_PATH_PREFIXES = ("/rest/v1/orchestrate", "/psops")


async def auth_middleware(request: Request, call_next):
    """Shared account identity with explicit public-API Bearer transport.

    Internal API (``/rest/v1/orchestrate/*``) and the legacy ``/psops`` alias:
        Token-based auth via database-backed users.  Public auth endpoints
        (login/check/register) are exempt.

    External API (``/api/v1/*``):
        Defaults to the same login-token validation. Direct integrations may
        explicitly select legacy machine authentication. Browser gateways never
        use their own TLS certificate as the original caller's identity.
    """
    path = request.url.path
    from orchestrate.server.gateway_policy import is_browser_gateway_request
    browser_gateway = is_browser_gateway_request(request)

    # CORS preflight always allowed.
    if request.method == "OPTIONS":
        return await call_next(request)

    if path == "/api/v1/auth/token" and request.method == "POST":
        # Only credential verification/token issuance is anonymous, not /auth/*.
        return await call_next(request)

    if path == "/api/v1" or path.startswith("/api/v1/"):
        from orchestrate.server.external_auth import authenticate_external
        conf = get_conf()
        try:
            if path == "/api/v1/auth/logout":
                require_user_authentication()
                request.state.user_identity = require_session_identity(
                    request, allow_cookie=False, allow_password_change=True)
            else:
                request.state.machine_identity = await authenticate_external(request, conf)
                if browser_gateway:
                    # A caller may forge this marker: add requirements,
                    # never select an alternative authentication provider.
                    require_user_authentication()
                    request.state.user_identity = require_session_identity(request, allow_cookie=False)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content=error(exc.status_code, exc.detail),
                                headers=exc.headers)
        return await call_next(request)

    # Only the internal API (and its legacy alias) needs application-layer auth.
    if not path.startswith(_PROTECTED_PATH_PREFIXES):
        return await call_next(request)

    try:
        auth_enabled = is_auth_enabled()
    except RuntimeError as e:
        # Fail closed: an unreachable user store must never be read as
        # "no users -> auth disabled", or a database outage would leave
        # every endpoint unauthenticated.
        logger.error(f"[Auth] Authentication backend unavailable: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error(503, "Authentication backend unavailable"),
        )
    except StorageError as e:
        mapped = storage_http_exception(e)
        return JSONResponse(status_code=mapped.status_code, content=error(mapped.status_code, mapped.detail))

    if not auth_enabled:
        return JSONResponse(status_code=503, content=error(503, "Account authentication is not configured"))

    if path in _PUBLIC_AUTH_PATHS:
        return await call_next(request)

    try:
        request.state.user_identity = require_session_identity(
            request, allow_password_change=path in _PASSWORD_CHANGE_EXEMPT_PATHS)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=error(exc.status_code, exc.detail,
                            data={"must_change_password": True} if exc.detail == "Password change required" else None),
                            headers=exc.headers)

    return await call_next(request)

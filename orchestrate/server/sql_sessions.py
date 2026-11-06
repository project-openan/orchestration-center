# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared, opaque account sessions. Tokens never persist in plaintext.

All account/session mutations serialize on the users row. The companion
identity row gives delete/recreate a new generation and fences in-flight
password checks without adding columns to legacy user schemas.
"""

from contextlib import contextmanager, suppress
import hashlib
import secrets
from uuid import uuid4

from fastapi import HTTPException

from database.utils.storage_errors import raise_storage_error, close_resource
from orchestrate.persistence.errors import StorageError


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@contextmanager
def _transaction(provider):
    conn = None
    cursor = None
    try:
        conn = provider.connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN")
        yield cursor
        conn.commit()
    except (HTTPException, StorageError):
        if conn is not None:
            with suppress(Exception):
                conn.rollback()
        raise
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        if conn is None:
            from orchestrate.persistence.errors import StorageUnavailableError

            raise StorageUnavailableError("Shared authentication backend unavailable") from exc
        raise_storage_error(exc, "Shared account session operation")
    finally:
        if cursor is not None:
            close_resource(cursor)
        if conn is not None:
            close_resource(conn)


def ensure_auth_schema(provider):
    """Idempotent startup schema, also used by direct ASGI composition."""
    with provider._lock:
        if getattr(provider, "shared_auth_ready", False):
            return
        with _transaction(provider) as cur:
            options = (
                " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin" if provider.mode == "mysql" else ""
            )
            cur.execute("""CREATE TABLE IF NOT EXISTS account_auth_state (
                username VARCHAR(64) PRIMARY KEY,
                generation VARCHAR(36) NOT NULL UNIQUE,
                auth_version BIGINT NOT NULL
            )""" + options)
            cur.execute("""CREATE TABLE IF NOT EXISTS account_sessions (
                token_hash VARCHAR(64) PRIMARY KEY,
                username VARCHAR(64) NOT NULL,
                generation VARCHAR(36) NOT NULL,
                auth_version BIGINT NOT NULL,
                role VARCHAR(16) NOT NULL,
                expires_at BIGINT NOT NULL
            )""" + options)
        provider.shared_auth_ready = True


def check_auth_schema(provider):
    with _transaction(provider) as cur:
        cur.execute("SELECT username,generation,auth_version FROM account_auth_state WHERE 1=0")
        cur.execute(
            "SELECT token_hash,username,generation,auth_version,role,expires_at FROM account_sessions WHERE 1=0"
        )
    provider.shared_auth_ready = True


def shared_store(provider):
    ensure_auth_schema(provider)
    with provider._lock:
        store = getattr(provider, "_shared_session_store", None)
        if store is None:
            store = SqlSessionStore(provider)
            provider._shared_session_store = store
        return store


class SqlSessionStore:
    """Instance-bound sessions; every read uses the shared authority."""

    def __init__(self, provider):
        self.provider = provider

    @staticmethod
    def login_revision():
        # SQL uses the verified per-user snapshot instead of a process counter.
        return None

    @staticmethod
    def _user_locked(cur, username):
        cur.execute(
            "SELECT username, password_hash, salt, role, "
            "must_change_password, password_scheme FROM users "
            "WHERE username = %s FOR UPDATE",
            (username,),
        )
        return cur.fetchone()

    @staticmethod
    def _state_locked(cur, username):
        cur.execute(
            "SELECT generation, auth_version FROM account_auth_state " "WHERE username = %s FOR UPDATE", (username,)
        )
        row = cur.fetchone()
        if row is None:
            row = (str(uuid4()), 0)
            cur.execute(
                "INSERT INTO account_auth_state (username, generation, auth_version) " "VALUES (%s, %s, %s)",
                (username, *row),
            )
        return row

    def authenticate(self, username, password):
        from database.utils.user_store import _verify_password

        # Short lock: freeze credentials and version before expensive verification.
        with _transaction(self.provider) as cur:
            row = self._user_locked(cur, username)
            if row is None:
                return None
            generation, version = self._state_locked(cur, username)
            snapshot = {
                "generation": generation,
                "version": version,
                "role": row[3],
                "must_change_password": bool(row[4]),
            }
        if not _verify_password(row[1], row[2], row[5] or "legacy", password):
            return None
        # A same-password hash upgrade is not a security-version change. It uses
        # its existing CAS, so concurrent password changes are never overwritten.
        from database.utils.user_store import _CURRENT_PASSWORD_SCHEME, _upgrade_password_scheme

        if row[5] != _CURRENT_PASSWORD_SCHEME:
            from database.utils.connection_provider import connection_scope

            try:
                with connection_scope(self.provider):
                    _upgrade_password_scheme(username, password, row[1], row[2], row[5])
            except StorageError:
                pass  # Opportunistic upgrade does not turn a valid password invalid.
        return {"username": row[0], "role": row[3], "must_change_password": bool(row[4]), "_auth_snapshot": snapshot}

    def _now(self, cur):
        cur.execute(
            "SELECT UNIX_TIMESTAMP()"
            if self.provider.mode == "mysql"
            else "SELECT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)"
        )
        return int(cur.fetchone()[0])

    def create(self, username, role="user", *, login_revision=None, credential_snapshot=None):
        from orchestrate.server.auth import _get_ttl

        if not isinstance(credential_snapshot, dict):
            raise HTTPException(401, "Account changed during login; please log in again")
        token = secrets.token_urlsafe(32)
        ttl = _get_ttl()
        with _transaction(self.provider) as cur:
            user = self._user_locked(cur, username)
            if user is None:
                raise HTTPException(401, "Account changed during login; please log in again")
            generation, version = self._state_locked(cur, username)
            current = {
                "generation": generation,
                "version": version,
                "role": user[3],
                "must_change_password": bool(user[4]),
            }
            if credential_snapshot != current or role != user[3] or role not in {"admin", "user"}:
                raise HTTPException(401, "Account changed during login; please log in again")
            expires_at = self._now(cur) + ttl
            cur.execute(
                "INSERT INTO account_sessions "
                "(token_hash, username, generation, auth_version, role, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (_token_hash(token), username, generation, version, role, expires_at),
            )
        return token, ttl

    def identity(self, token):
        if not token:
            return None
        from orchestrate.server.auth import SessionIdentity

        with _transaction(self.provider) as cur:
            now = self._now(cur)
            cur.execute(
                "SELECT s.username, s.role, u.must_change_password, a.generation FROM account_sessions s "
                "JOIN account_auth_state a ON a.username = s.username "
                "AND a.generation = s.generation AND a.auth_version = s.auth_version "
                "JOIN users u ON u.username = s.username AND u.role = s.role "
                "WHERE s.token_hash = %s AND s.expires_at > %s",
                (_token_hash(token), now),
            )
            row = cur.fetchone()
        return SessionIdentity(*row) if row else None

    def validate(self, token):
        return self.identity(token) is not None

    def get_username(self, token):
        identity = self.identity(token)
        return identity.username if identity else None

    def get_role(self, token):
        identity = self.identity(token)
        return identity.role if identity else None

    def requires_password_change(self, username):
        with _transaction(self.provider) as cur:
            cur.execute("SELECT must_change_password FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
        return bool(row[0]) if row else False

    def subject_authorized(self, subject_id, role):
        """Recheck a queued job without retaining a session token.

        A broader current role does not broaden the job's frozen role. A
        recreated username has a different generation and cannot inherit it.
        """
        if role not in {"user", "admin"} or not subject_id:
            return False
        with _transaction(self.provider) as cur:
            cur.execute(
                "SELECT u.role, u.must_change_password FROM users u "
                "JOIN account_auth_state a ON a.username = u.username "
                "WHERE a.generation = %s",
                (subject_id,),
            )
            row = cur.fetchone()
        return bool(row and not row[1] and row[0] in {"user", "admin"} and (role != "admin" or row[0] == "admin"))

    def revoke(self, token):
        if token:
            with _transaction(self.provider) as cur:
                cur.execute("DELETE FROM account_sessions WHERE token_hash = %s", (_token_hash(token),))

    def revoke_user(self, username):
        with _transaction(self.provider) as cur:
            if self._user_locked(cur, username) is None:
                return
            self._state_locked(cur, username)
            self._invalidate_locked(cur, username)

    @staticmethod
    def _invalidate_locked(cur, username):
        cur.execute("UPDATE account_auth_state SET auth_version = auth_version + 1 " "WHERE username = %s", (username,))
        cur.execute("DELETE FROM account_sessions WHERE username = %s", (username,))

    def update_password(self, username, new_password, *, expected_snapshot=None):
        from database.utils.user_store import _hash_password_bcrypt, _CURRENT_PASSWORD_SCHEME

        hashed = _hash_password_bcrypt(new_password)
        with _transaction(self.provider) as cur:
            user = self._user_locked(cur, username)
            if user is None:
                return False
            generation, version = self._state_locked(cur, username)
            if expected_snapshot is not None and expected_snapshot != {
                "generation": generation,
                "version": version,
                "role": user[3],
                "must_change_password": bool(user[4]),
            }:
                raise HTTPException(409, "Account changed during password update; please log in again")
            cur.execute(
                "UPDATE users SET password_hash = %s, salt = %s, "
                "must_change_password = FALSE, password_scheme = %s WHERE username = %s",
                (hashed, "", _CURRENT_PASSWORD_SCHEME, username),
            )
            self._invalidate_locked(cur, username)
        return True

    def change_password(self, username, old_password, new_password):
        account = self.authenticate(username, old_password)
        if account is None:
            raise HTTPException(401, "Current password is incorrect")
        return self.update_password(username, new_password, expected_snapshot=account["_auth_snapshot"])

    def delete_account(self, username):
        with _transaction(self.provider) as cur:
            if self._user_locked(cur, username) is None:
                return False
            cur.execute("DELETE FROM account_sessions WHERE username = %s", (username,))
            cur.execute("DELETE FROM account_auth_state WHERE username = %s", (username,))
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
        return True


class LegacyAuthProvider:
    """Keep standalone legacy helpers on their original connection source.

    A short-lived wrapper deliberately does not cache readiness across changes
    to a legacy global pool. HTTP repositories use their bound provider instead.
    """

    def __init__(self, mode, factory):
        import threading

        self.mode = mode
        self.factory = factory
        self._lock = threading.RLock()

    def connection(self):
        from database.utils.connection_provider import connection_scope

        with connection_scope(None):
            connection = self.factory()
        if connection is None:
            from orchestrate.persistence.errors import StorageUnavailableError

            raise StorageUnavailableError("Shared authentication backend unavailable")
        return connection

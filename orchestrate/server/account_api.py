# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""First-party account Bearer tokens, not an OAuth password-grant server."""

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from orchestrate.persistence import current_context
from orchestrate.persistence.errors import StorageError
from orchestrate.server import auth
from orchestrate.server.account_auth import AccountLogin, authenticate_account
from orchestrate.server.middleware import LoginRateLimiter
from orchestrate.server.storage_error_response import storage_http_exception

router = APIRouter(prefix="/api/v1/auth")
_login_limit = LoginRateLimiter(auth.get_conf())
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.post("/token")
async def issue_token(payload: AccountLogin, _: bool = Depends(_login_limit)):
    auth.require_user_authentication()
    store = auth.get_session_store()
    revision = store.login_revision()
    try:
        user = await anyio.to_thread.run_sync(
            lambda: authenticate_account(payload.username, payload.password,
                                         conf=auth.get_conf(), storage=current_context()))
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    username = user["username"]
    if user.get("must_change_password", False):
        auth.mark_must_change_password(username)
        raise HTTPException(403, "Password change required; use the web login to change it")
    token, ttl = auth.create_account_session(store, user, revision)
    auth.clear_must_change_password(username)
    return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": ttl},
                        headers=_NO_STORE)


@router.post("/logout")
async def revoke_token(request: Request):
    # API logout revokes the explicit Bearer, never an unrelated browser cookie.
    auth.require_session_identity(request, allow_cookie=False, allow_password_change=True)
    auth.get_session_store().revoke(auth.extract_bearer_token(request))
    return JSONResponse({"revoked": True}, headers=_NO_STORE)

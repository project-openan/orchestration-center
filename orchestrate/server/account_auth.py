# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Account verification shared by cookie login and programmatic token issuance."""

import hashlib
import secrets

from fastapi import HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from common.util.password_hash import FILE_HASH_PREFIX, verify_legacy_bcrypt, verify_password


class AccountLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Same account as web login")
    password: str = Field(..., min_length=1, max_length=256, description="Plaintext password; use a public HTTPS endpoint")


def verify_access_password(stored: str, plaintext: str) -> bool:
    """Accept current file hashes and the documented legacy hash formats."""
    if not stored:
        return False
    if stored.startswith(FILE_HASH_PREFIX):
        return verify_password(plaintext, stored[len(FILE_HASH_PREFIX):])
    if stored.startswith("$2"):
        return verify_legacy_bcrypt(plaintext, stored)
    return secrets.compare_digest(hashlib.sha256(plaintext.encode()).hexdigest(), stored)


def authenticate_account(username: str, password: str, *, conf: dict, storage) -> dict:
    """Verify one account; callers own session issuance and transport details."""
    if storage.has_users:
        user = storage.users.authenticate(username, password)
    else:
        # Verify the password before looking at the username, so a wrong
        # username costs the same as a wrong password (#205).
        password_ok = verify_access_password(conf.get("access_password", ""), password)
        if username == "admin" and password_ok:
            user = {"username": "admin", "role": "admin", "must_change_password": False}
        else:
            user = None
    if user is None:
        # Preserve failure visibility without logging credentials or untrusted
        # account strings (which can contain newlines in a rejected request).
        logger.warning("Account login failed: invalid credentials")
        raise HTTPException(401, "Incorrect username or password")
    if not user.get("username") or user.get("role", "user") not in {"user", "admin"}:
        raise HTTPException(403, "Account role is not permitted")
    return user

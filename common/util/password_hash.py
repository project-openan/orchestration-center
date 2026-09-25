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

"""Versioned password hashing shared by database and file-mode auth."""

import hashlib

import bcrypt


PASSWORD_SCHEME = "v4"
FILE_HASH_PREFIX = "v4:"


def _bcrypt_input(password: str) -> bytes:
    # bcrypt accepts at most 72 bytes. A domain-separated SHA-256 hex digest
    # has a fixed 64-byte length and preserves the full UTF-8 password.
    return hashlib.sha256(b"openan-password-v4\0" + password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(password), stored_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def verify_legacy_bcrypt(password: str, stored_hash: str) -> bool:
    """Verify v3 hashes, including passwords bcrypt 4 silently truncated."""
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], stored_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False

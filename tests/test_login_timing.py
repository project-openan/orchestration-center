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

"""#205: a login for an unknown username must cost the same as a wrong password.

Every backend used to return early for an unknown account, before any
password hash was checked, so response time revealed which usernames exist.
"""

import statistics
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import bcrypt
import pytest
from fastapi import HTTPException

from common.util import password_hash
from common.util.password_hash import FILE_HASH_PREFIX, burn_password_check, hash_password
from database.utils import user_store
from orchestrate.server.account_auth import authenticate_account
from orchestrate.server.sql_sessions import SqlSessionStore


def _cost(bcrypt_hash):
    return int(bcrypt_hash.split("$")[2])


class TestBurnPasswordCheck:
    def test_always_false(self):
        assert burn_password_check("anything") is False
        assert burn_password_check("") is False

    def test_dummy_hash_uses_the_real_scheme_and_cost(self):
        burn_password_check("x")
        assert _cost(password_hash._dummy_hash) == _cost(hash_password("real-password"))

    def test_runs_a_real_bcrypt_check(self):
        with patch.object(password_hash.bcrypt, "checkpw", wraps=bcrypt.checkpw) as spy:
            burn_password_check("guess")
        spy.assert_called_once()

    def test_tolerates_non_string_input(self):
        assert burn_password_check(None) is False


class TestUnknownAccountSpendsAVerification:
    def test_file_mode_checks_password_for_any_username(self):
        conf = {"access_password": FILE_HASH_PREFIX + hash_password("Correct#Horse1")}
        storage = SimpleNamespace(has_users=False)
        with patch("orchestrate.server.account_auth.verify_password",
                   wraps=password_hash.verify_password) as spy, pytest.raises(HTTPException) as exc:
            authenticate_account("zzz_nonexistent_zzz", "Correct#Horse1", conf=conf, storage=storage)
        assert exc.value.status_code == 401
        spy.assert_called_once()

    def test_file_mode_right_password_wrong_username_still_rejected(self):
        conf = {"access_password": FILE_HASH_PREFIX + hash_password("Correct#Horse1")}
        with pytest.raises(HTTPException) as exc:
            authenticate_account("root", "Correct#Horse1", conf=conf, storage=SimpleNamespace(has_users=False))
        assert exc.value.status_code == 401

    def test_file_mode_admin_still_logs_in(self):
        conf = {"access_password": FILE_HASH_PREFIX + hash_password("Correct#Horse1")}
        user = authenticate_account("admin", "Correct#Horse1", conf=conf, storage=SimpleNamespace(has_users=False))
        assert user["username"] == "admin" and user["role"] == "admin"

    def test_user_store_unknown_user(self):
        with patch.object(user_store, "_shared_auth_store", return_value=None), \
             patch.object(user_store, "create_connection", return_value=MagicMock()), \
             patch.object(user_store, "execute_query", return_value=([], None)), \
             patch.object(user_store, "burn_password_check", wraps=burn_password_check) as spy:
            assert user_store.authenticate_user("ghost", "pw") is None
        spy.assert_called_once_with("pw")

    def test_sql_session_store_unknown_user(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        provider = MagicMock()
        provider.connection.return_value.cursor.return_value = cursor
        with patch.object(password_hash, "verify_password", wraps=password_hash.verify_password) as spy:
            assert SqlSessionStore(provider).authenticate("ghost", "pw") is None
        spy.assert_called_once()
        provider.connection.return_value.commit.assert_called_once()


@pytest.mark.parametrize("scheme", ["legacy", "v2"])
def test_fast_legacy_schemes_also_spend_a_bcrypt_check(scheme):
    """Unmigrated SHA-256 accounts must not answer faster than unknown ones."""
    with patch.object(user_store, "burn_password_check", wraps=burn_password_check) as spy:
        assert user_store._verify_password("0" * 64, "salt", scheme, "wrong") is False
    spy.assert_called_once()


def test_legacy_scheme_correct_password_still_verifies():
    stored = user_store._hash_password("Pw#12345", "salt")
    assert user_store._verify_password(stored, "salt", "v2", "Pw#12345") is True


def _median_seconds(fn, rounds=5):
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        with pytest.raises(HTTPException):
            fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def test_file_mode_timing_no_longer_distinguishes_usernames():
    """End-to-end through authenticate_account with a real bcrypt credential."""
    conf = {"access_password": FILE_HASH_PREFIX + hash_password("Correct#Horse1")}
    storage = SimpleNamespace(has_users=False)
    burn_password_check("warm-up")

    known = _median_seconds(lambda: authenticate_account("admin", "wrong", conf=conf, storage=storage))
    unknown = _median_seconds(lambda: authenticate_account("zzz_nonexistent_zzz", "wrong",
                                                           conf=conf, storage=storage))
    # Before the fix the unknown path skipped bcrypt entirely (~1000x faster).
    assert unknown > known * 0.5, (known, unknown)

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

"""Regression coverage for #39: every request logged its raw query params,
including access_token -- the SSE execution stream puts the session token
there because EventSource can't set an Authorization header. That wrote a
live, still-valid bearer token into the application log on every workflow
execution.
"""

import os

os.environ.setdefault("TESTING", "True")

from orchestrate.server.frontend_support_server import _redact_sensitive_params


class TestRedactSensitiveParams:
    def test_redacts_access_token(self):
        result = _redact_sensitive_params({"access_token": "live-session-token-abc123"})
        assert result == {"access_token": "***"}

    def test_redacts_token(self):
        result = _redact_sensitive_params({"token": "live-session-token-abc123"})
        assert result == {"token": "***"}

    def test_redacts_password_and_api_key_and_secret(self):
        result = _redact_sensitive_params({
            "password": "hunter2", "api_key": "sk-abc", "secret": "shh",
        })
        assert result == {"password": "***", "api_key": "***", "secret": "***"}

    def test_redacts_workflow_intent_from_legacy_get_urls(self):
        result = _redact_sensitive_params({
            "psop_id": "psop-1", "user_intent": "private customer request",
            "intent": "private dispatch request", "task": "private external request",
        })
        assert result == {
            "psop_id": "psop-1", "user_intent": "***",
            "intent": "***", "task": "***",
        }

    def test_redaction_is_case_insensitive(self):
        result = _redact_sensitive_params({"Access_Token": "live-token", "TOKEN": "live-token"})
        assert result == {"Access_Token": "***", "TOKEN": "***"}

    def test_leaves_non_sensitive_params_untouched(self):
        result = _redact_sensitive_params({"psop_id": "abc-123", "lang": "en"})
        assert result == {"psop_id": "abc-123", "lang": "en"}

    def test_mixed_params_only_redacts_sensitive_keys(self):
        result = _redact_sensitive_params({"psop_id": "abc-123", "access_token": "live-token"})
        assert result == {"psop_id": "abc-123", "access_token": "***"}

    def test_empty_params(self):
        assert _redact_sensitive_params({}) == {}

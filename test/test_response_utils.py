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

import pytest
from unittest.mock import MagicMock, patch

from orchestrate.server.response_utils import ok, created


class TestOk:
    def test_returns_standard_envelope(self):
        result = ok(data={"key": "value"})
        assert result["code"] == 200
        assert result["message"] == "success"
        assert result["status"] == "success"
        assert result["data"] == {"key": "value"}

    def test_custom_message(self):
        result = ok(data=[1, 2], message="done")
        assert result["code"] == 200
        assert result["message"] == "done"
        assert result["data"] == [1, 2]

    def test_none_data(self):
        result = ok(data=None)
        assert result["code"] == 200
        assert result["data"] is None

    def test_no_data_argument(self):
        result = ok()
        assert result["code"] == 200
        assert result["data"] is None


class TestCreated:
    def test_returns_201_envelope(self):
        result = created(data={"id": "abc"})
        assert result["code"] == 201
        assert result["message"] == "created"
        assert result["status"] == "success"
        assert result["data"] == {"id": "abc"}

    def test_custom_message(self):
        result = created(data=None, message="workflow saved")
        assert result["code"] == 201
        assert result["message"] == "workflow saved"

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
"""Coverage for common.llm.llm instance factory error paths and placeholders."""

import pytest

from common.llm import llm
from common.llm.config.llm_config import ModelConfig


@pytest.fixture(autouse=True)
def _reset_instances():
    llm._instances.clear()
    yield
    llm._instances.clear()


def test_has_input_placeholder_returns_false_for_non_string_scalars():
    assert llm._has_input_placeholder(123) is False
    assert llm._has_input_placeholder(None) is False


def test_has_input_placeholder_descends_into_containers():
    assert llm._has_input_placeholder({"k": [123, 456]}) is False
    assert llm._has_input_placeholder({"k": "$PROMPT"}) is True


def test_get_llm_instance_raises_when_capability_unconfigured(monkeypatch):
    monkeypatch.setattr(llm, "get_model_config", lambda capability: None)
    with pytest.raises(ValueError, match="No model configured for capability 'embed'"):
        llm.get_llm_instance("embed")


def test_get_embed_instance_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(llm, "get_model_config", lambda capability: None)
    with pytest.raises(ValueError, match="No model configured"):
        llm.get_embed_instance()


def test_get_rerank_instance_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(llm, "get_model_config", lambda capability: None)
    with pytest.raises(ValueError, match="No model configured"):
        llm.get_rerank_instance()


def test_get_chat_instance_with_body_raises_when_chat_unconfigured(monkeypatch):
    monkeypatch.setattr(llm, "get_model_config", lambda capability: None)
    with pytest.raises(ValueError, match="No model configured for capability 'chat'"):
        llm.get_chat_instance_with_body("cache-key", {})


def test_get_chat_instance_with_body_raises_when_required_fields_missing(monkeypatch):
    # url/model placeholders are rejected before a client is built.
    config = ModelConfig(model="<YOUR_VALUE>", url="http://localhost")
    monkeypatch.setattr(llm, "get_model_config", lambda capability: config)
    with pytest.raises(ValueError, match="not configured"):
        llm.get_chat_instance_with_body("missing-fields", {})

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Retrieval-only provider options must not alter the shared chat contract."""

from unittest.mock import patch

import json
import httpx
import pytest

from common.llm import llm
from common.llm.config.llm_config import ModelConfig


def test_real_chat_clients_render_separate_retrieval_and_shared_request_bodies():
    config = ModelConfig(model="synthetic", url="https://example.invalid/chat", body={
        "model": "$MODEL", "messages": [{"role": "user", "content": "$PROMPT"}],
        "thinking": {"type": "enabled"},
    }, response={"answer": "choices[0].message.content"})
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})

    clients = []
    with patch.dict(llm._instances, {}, clear=True), patch.object(llm, "get_model_config", return_value=config):
        try:
            clients.append(llm.get_chat_instance_with_body("test", {"thinking": {"type": "disabled"}}))
            clients.append(llm.get_llm_instance())
            for client in clients:
                client._client.close()
                client._client = httpx.Client(transport=httpx.MockTransport(respond))
                assert client.ask_llm("synthetic intent") == ("", "[]")
        finally:
            for client in clients:
                client._client.close()
    assert [body["thinking"]["type"] for body in requests] == ["disabled", "enabled"]
    assert all(body["model"] == "synthetic" for body in requests)
    assert all(body["messages"] == [{"role": "user", "content": "synthetic intent"}] for body in requests)


def test_existing_thinking_option_can_be_overridden_without_mutating_shared_config():
    config = ModelConfig(model="synthetic", url="https://example.invalid/chat", body={
        "model": "$MODEL", "messages": [{"role": "user", "content": "$PROMPT"}],
        "thinking": {"type": "enabled"},
    })
    with patch.dict(llm._instances, {}, clear=True), \
         patch.object(llm, "get_model_config", return_value=config), \
         patch.object(llm, "GenericLLM") as factory:
        client = llm.get_chat_instance_with_body("test", {"thinking": {"type": "disabled"}})
        assert client is factory.return_value
        assert factory.call_args.args[0]["body"]["thinking"] == {"type": "disabled"}
        assert config.body["thinking"] == {"type": "enabled"}


@pytest.mark.parametrize("field", ["model", "messages", "input", "query", "documents", "stream", "custom_prompt", "auth_token"])
def test_protocol_inputs_and_profile_placeholders_cannot_be_overridden(field):
    config = ModelConfig(model="synthetic", url="https://example.invalid/chat", body={
        "custom_prompt": {"text": "$PROMPT"},
        "auth_token": "$API_KEY",
    })
    with patch.dict(llm._instances, {}, clear=True), \
         patch.object(llm, "get_model_config", return_value=config), \
         patch.object(llm, "GenericLLM") as factory:
        with pytest.raises(ValueError, match="reserved fields"):
            llm.get_chat_instance_with_body("test", {field: "replacement"})
        factory.assert_not_called()

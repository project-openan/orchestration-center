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

from common.llm.config.llm_config import ModelConfig, get_model_config
from common.llm.provider.auth_strategies import AUTH_STRATEGIES, _build_aoc_signed_headers
from common.llm.provider.generic_llm import GenericLLM

CHAT_CONFIG = dict(
    description="test chat model",
    model="test-chat",
    url="http://localhost:1234/v1/chat",
    api_key="sk-test",
    enable_thinking=True,
    auth=None,
    headers={},
    body={"model": "$MODEL", "messages": [{"role": "user", "content": "$PROMPT"}]},
    response={"answer": "choices[0].message.content", "reasoning": "choices[0].message.reasoning_content"},
)

EMBED_CONFIG = dict(
    description="test embed model",
    model="test-embed",
    url="http://localhost:1234/v1/embed",
    api_key="",
    enable_thinking=False,
    auth=None,
    headers={},
    body={"model": "$MODEL", "input": "$PROMPT"},
    response={"embedding": "data[0].embedding"},
)

RERANK_CONFIG = dict(
    description="test rerank model",
    model="test-rerank",
    url="http://localhost:1234/v1/rerank",
    api_key="",
    enable_thinking=False,
    auth=None,
    headers={},
    body={"model": "$MODEL", "query": "$QUERY", "documents": "$DOCUMENTS"},
    response={"results": "results"},
)


# ── ModelConfig ──

class TestModelConfig:
    def test_from_dict_fills_all_fields(self):
        cfg = ModelConfig.from_dict("chat", CHAT_CONFIG)
        assert cfg.model == "test-chat"
        assert cfg.url == "http://localhost:1234/v1/chat"
        assert cfg.api_key == "sk-test"
        assert cfg.enable_thinking is True
        assert cfg.auth is None
        assert cfg.headers == {}
        assert cfg.body["model"] == "$MODEL"

    def test_defaults_for_missing_fields(self):
        cfg = ModelConfig.from_dict("x", {"url": "http://x"})
        assert cfg.model == ""
        assert cfg.api_key == ""
        assert cfg.enable_thinking is False
        assert cfg.auth is None
        assert cfg.headers == {}
        assert cfg.body == {}
        assert cfg.response == {}

    def test_auth_dict_preserved(self):
        auth_val = {"type": "aoc_signed", "app_key": "k", "app_secret": "s", "authorization": "Bearer x", "api_code": "c"}
        cfg = ModelConfig.from_dict("x", {"url": "", "auth": auth_val})
        assert cfg.auth == auth_val

    def test_auth_null_preserved(self):
        cfg = ModelConfig.from_dict("x", {"url": "", "auth": None})
        assert cfg.auth is None


# ── auth_strategies ──

AOC_PARAMS = {
    "app_key": "test-key",
    "app_secret": "test-secret",
    "authorization": "Bearer test-token",
    "api_code": "TEST-API",
}


class TestAOCSignedHeaders:
    def test_includes_all_required_headers(self):
        headers = _build_aoc_signed_headers(AOC_PARAMS)
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["x-sg-app-key"] == "test-key"
        assert headers["x-sg-api-code"] == "TEST-API"
        assert "x-sg-message-id" in headers
        assert len(headers["x-sg-message-id"]) == 32

    def test_each_call_generates_unique_message_id_and_signature(self):
        h1 = _build_aoc_signed_headers(AOC_PARAMS)
        h2 = _build_aoc_signed_headers(AOC_PARAMS)
        assert h1["x-sg-message-id"] != h2["x-sg-message-id"]
        assert h1["x-sg-md5-secret"] != h2["x-sg-md5-secret"]

    def test_default_scenario_and_ability_codes(self):
        headers = _build_aoc_signed_headers(AOC_PARAMS)
        assert headers["x-sg-scenario-code"] == "B99999999999"
        assert headers["x-sg-ability-code"] == "A999999999"
        assert headers["x-sg-api-version"] == "1.0"

    def test_missing_required_param_raises_keyerror(self):
        bad = {"app_key": "k"}  # missing app_secret, authorization, api_code
        with pytest.raises(KeyError):
            _build_aoc_signed_headers(bad)


# ── GenericLLM ──

class TestGenericLLMInit:
    def test_unknown_auth_type_raises(self):
        cfg = {**CHAT_CONFIG, "auth": {"type": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown auth type"):
            GenericLLM(cfg)

    def test_auth_string_type(self):
        cfg = {**CHAT_CONFIG, "auth": "aoc_signed", "auth_params": AOC_PARAMS}
        llm = GenericLLM(cfg)
        assert llm._auth_type == "aoc_signed"

    def test_auth_none_defaults(self):
        llm = GenericLLM(CHAT_CONFIG)
        assert llm._auth_type is None

    def test_to_dict(self):
        llm = GenericLLM(CHAT_CONFIG)
        assert llm.to_dict()["name"] == "test chat model"

    def test_to_dict_fallback_when_no_description(self):
        cfg = {**CHAT_CONFIG, "description": ""}
        llm = GenericLLM(cfg)
        assert llm.to_dict()["name"] == "test-chat"


class TestRenderBody:
    def test_replaces_model_and_prompt(self):
        llm = GenericLLM(CHAT_CONFIG)
        body = llm._render_body(prompt="hello world")
        assert body["model"] == "test-chat"
        assert body["messages"][0]["content"] == "hello world"

    def test_enable_thinking_renders_as_bool(self):
        cfg = {
            **CHAT_CONFIG,
            "body": {"model": "$MODEL", "chat_template_kwargs": {"enable_thinking": "$ENABLE_THINKING"}},
        }
        llm = GenericLLM(cfg)
        body = llm._render_body(prompt="hi")
        tk = body["chat_template_kwargs"]["enable_thinking"]
        assert isinstance(tk, bool)
        assert tk is True

        cfg["enable_thinking"] = False
        llm2 = GenericLLM(cfg)
        body2 = llm2._render_body(prompt="hi")
        assert body2["chat_template_kwargs"]["enable_thinking"] is False

    def test_model_placeholder_case_insensitive_via_ctx_keys(self):
        cfg = {**CHAT_CONFIG, "model": "lower-case-model"}
        llm = GenericLLM(cfg)
        body = llm._render_body(prompt="hi")
        assert body["model"] == "lower-case-model"

    def test_embed_body(self):
        llm = GenericLLM(EMBED_CONFIG)
        body = llm._render_body(prompt="embed this")
        assert body["input"] == "embed this"

    def test_rerank_body_with_documents_list(self):
        llm = GenericLLM(RERANK_CONFIG)
        body = llm._render_body(query="test q", documents=["d1", "d2"])
        assert body["query"] == "test q"
        assert isinstance(body["documents"], list)
        assert body["documents"] == ["d1", "d2"]

    def test_does_not_mutate_template(self):
        llm = GenericLLM(CHAT_CONFIG)
        original = llm._body_template["model"]
        llm._render_body(prompt="hi")
        assert llm._body_template["model"] == "$MODEL"


class TestExtract:
    @pytest.fixture
    def llm(self):
        return GenericLLM(CHAT_CONFIG)

    def test_simple_path(self, llm):
        data = {"result": "ok"}
        cfg = GenericLLM({**CHAT_CONFIG, "response": {"answer": "result"}})
        assert cfg._extract(data, "answer") == "ok"

    def test_dotted_path(self, llm):
        data = {"choices": [{"message": {"content": "hello"}}]}
        assert llm._extract(data, "answer") == "hello"

    def test_missing_key(self, llm):
        assert llm._extract({}, "answer") is None

    def test_missing_intermediate_key(self, llm):
        data = {"choices": []}
        assert llm._extract(data, "answer") is None

    def test_embedding_path(self):
        llm = GenericLLM(EMBED_CONFIG)
        data = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        assert llm._extract(data, "embedding") == [0.1, 0.2, 0.3]

    def test_rerank_path(self):
        llm = GenericLLM(RERANK_CONFIG)
        data = {"results": [{"index": 0, "relevance_score": 0.95}]}
        assert llm._extract(data, "results") == [{"index": 0, "relevance_score": 0.95}]

    def test_unconfigured_key_returns_none(self):
        llm = GenericLLM(CHAT_CONFIG)
        assert llm._extract({"x": 1}, "nonexistent") is None


class TestBuildHeaders:
    def test_no_auth_adds_bearer_if_api_key_present(self):
        llm = GenericLLM(CHAT_CONFIG)
        headers = llm._build_headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_no_auth_no_api_key_no_authorization(self):
        cfg = {**CHAT_CONFIG, "api_key": ""}
        llm = GenericLLM(cfg)
        headers = llm._build_headers()
        assert "Authorization" not in headers

    def test_auth_headers_merged(self):
        cfg = {
            **CHAT_CONFIG,
            "auth": "aoc_signed",
            "auth_params": AOC_PARAMS,
        }
        llm = GenericLLM(cfg)
        headers = llm._build_headers()
        assert headers["x-sg-app-key"] == "test-key"
        assert headers["Authorization"] == "Bearer test-token"

    def test_static_extra_headers_appended(self):
        cfg = {**CHAT_CONFIG, "headers": {"X-Custom": "val"}}
        llm = GenericLLM(cfg)
        headers = llm._build_headers()
        assert headers["X-Custom"] == "val"

    def test_auth_strategy_takes_precedence_over_api_key_authorization(self):
        cfg = {
            **CHAT_CONFIG,
            "auth": "aoc_signed",
            "auth_params": AOC_PARAMS,
        }
        llm = GenericLLM(cfg)
        headers = llm._build_headers()
        assert headers["Authorization"] == "Bearer test-token"


class TestAskLLM:
    def test_success_returns_reasoning_and_answer(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "answer", "reasoning_content": "think"}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(CHAT_CONFIG)
            reasoning, answer = llm.ask_llm("hello")
            assert answer == "answer"
            assert reasoning == "think"

    def test_exception_returns_empty(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.post.side_effect = Exception("network error")
            mock_client_class.return_value = mock_client

            llm = GenericLLM(CHAT_CONFIG)
            reasoning, answer = llm.ask_llm("hello")
            assert answer == ""
            assert reasoning == ""

    def test_missing_reasoning_returns_empty_string(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "answer"}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(CHAT_CONFIG)
            reasoning, answer = llm.ask_llm("hello")
            assert answer == "answer"
            assert reasoning == ""

    def test_body_uses_rendered_template(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(CHAT_CONFIG)
            llm.ask_llm("my prompt")
            sent_body = mock_client.post.call_args[1]["json"]
            assert sent_body["messages"][0]["content"] == "my prompt"


class TestEmbed:
    def test_success_returns_embedding_vector(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(EMBED_CONFIG)
            result = llm.embed("test text")
            assert result == [0.1, 0.2, 0.3]

    def test_missing_embedding_returns_empty(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"wrong": "format"}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(EMBED_CONFIG)
            result = llm.embed("test")
            assert result == []

    def test_network_error_returns_empty(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.post.side_effect = Exception("connection refused")
            mock_client_class.return_value = mock_client

            llm = GenericLLM(EMBED_CONFIG)
            result = llm.embed("test")
            assert result == []


class TestRerank:
    def test_success_returns_rerank_results(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "results": [{"index": 0, "relevance_score": 0.99}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(RERANK_CONFIG)
            result = llm.rerank("query", ["doc1", "doc2"])
            assert result == [{"index": 0, "relevance_score": 0.99}]

    def test_body_includes_query_and_documents(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"results": []}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(RERANK_CONFIG)
            llm.rerank("my query", ["d1", "d2"])
            sent_body = mock_client.post.call_args[1]["json"]
            assert sent_body["query"] == "my query"
            assert sent_body["documents"] == ["d1", "d2"]

    def test_missing_results_returns_empty(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            llm = GenericLLM(RERANK_CONFIG)
            result = llm.rerank("q", ["d"])
            assert result == []

    def test_network_error_returns_empty(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.post.side_effect = Exception("connection refused")
            mock_client_class.return_value = mock_client

            llm = GenericLLM(RERANK_CONFIG)
            result = llm.rerank("q", ["d"])
            assert result == []


class TestInstanceReuse:
    def test_multiple_ask_llm_calls_reuse_client(self):
        with patch('common.llm.provider.generic_llm.httpx.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"choices": [{"message": {"content": "x"}}]}
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_class.return_value = mock_client

            llm = GenericLLM(CHAT_CONFIG)
            llm.ask_llm("a")
            llm.ask_llm("b")
            assert mock_client.post.call_count == 2

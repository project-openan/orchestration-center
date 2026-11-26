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

import dataclasses
from common.llm.config.llm_config import (
    describe_missing_fields,
    get_model_config,
    missing_required_fields,
)
from common.llm.provider.generic_llm import GenericLLM

_instances = {}


def _has_input_placeholder(value) -> bool:
    """Profile-owned request inputs stay protected even with custom wire keys."""
    if isinstance(value, str):
        return any(token in value for token in ("$MODEL", "$PROMPT", "$QUERY", "$DOCUMENTS", "$API_KEY"))
    if isinstance(value, dict):
        return any(_has_input_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_input_placeholder(item) for item in value)
    return False


def _get_instance(capability: str) -> GenericLLM:
    if capability not in _instances:
        config = get_model_config(capability)
        if config is None:
            raise ValueError(
                f"No model configured for capability '{capability}' "
                "(check etc/config/models.yaml or LLM_CONFIG_FILE)"
            )
        missing = missing_required_fields(config)
        if missing:
            raise ValueError(describe_missing_fields(capability, missing))
        _instances[capability] = GenericLLM(dataclasses.asdict(config))
    return _instances[capability]


def get_llm_instance(capability: str = "chat"):
    return _get_instance(capability)


def get_chat_instance_with_body(cache_key: str, extra_body: dict) -> GenericLLM:
    """Chat client whose request body carries deployment-specific options.

    Provider options (including existing thinking settings) may be overridden.
    Protocol inputs and profile-specific input templates cannot be replaced.
    """
    key = f"chat:{cache_key}"
    if key not in _instances:
        config = get_model_config("chat")
        if config is None:
            raise ValueError(
                "No model configured for capability 'chat' "
                "(check etc/config/models.yaml or LLM_CONFIG_FILE)"
            )
        missing = missing_required_fields(config)
        if missing:
            raise ValueError(describe_missing_fields("chat", missing))
        body = dataclasses.asdict(config)
        overrides = dict(extra_body or {})
        reserved = {
            "model", "messages", "input", "query", "documents", "stream",
        }
        reserved.update(name for name, value in body.get("body", {}).items()
                        if _has_input_placeholder(value))
        overlap = reserved.intersection(overrides)
        if overlap:
            raise ValueError(f"chat: body overrides reserved fields: {', '.join(sorted(overlap))}")
        body["body"] = {**body.get("body", {}), **overrides}
        _instances[key] = GenericLLM(body)
    return _instances[key]


def get_embed_instance():
    return _get_instance("embed")


def get_rerank_instance():
    return _get_instance("rerank")


def reset_instances() -> None:
    """Drop cached clients and the cached config.

    Test-only helper, deliberately not re-exported from `common.llm` — both caches
    live for the process lifetime, so in production a configuration change takes
    effect on restart and nothing should be resetting them at runtime.
    """
    from common.llm.config.llm_config import _ModelConfigHolder

    _instances.clear()
    _ModelConfigHolder.reset()

if __name__ == "__main__":
    # Test Chat model
    llm = get_llm_instance()
    assert llm is not None, "LLM get instance faild"
    print(f"current Chat model: {llm.to_dict()}")
    reasoning, result = llm.ask_llm("what's the weather today？")
    print(result)
    print(reasoning)

    # Test Embedding model
    emb = get_embed_instance()
    print(f"current Embedding model: {emb.to_dict()}")
    embed_vector = emb.embed("what is the current document")
    print(embed_vector)

    # Test Reranker model
    rerank = get_rerank_instance()
    print(f"current Reranker model: {rerank.to_dict()}")
    rerank_result = rerank.rerank("ABC", ["ABCD", "BCDE"])
    print(rerank_result)

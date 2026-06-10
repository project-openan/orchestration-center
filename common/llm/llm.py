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
from common.llm.config.llm_config import get_model_config
from common.llm.provider.generic_llm import GenericLLM

_instances = {}


def _get_instance(capability: str) -> GenericLLM:
    if capability not in _instances:
        config = get_model_config(capability)
        if config is None:
            raise ValueError(
                f"No model configured for capability '{capability}' "
                f"in llm_config.json"
            )
        _instances[capability] = GenericLLM(dataclasses.asdict(config))
    return _instances[capability]


def get_llm_instance(capability: str = "chat"):
    return _get_instance(capability)


def get_embed_instance():
    return _get_instance("embed")


def get_rerank_instance():
    return _get_instance("rerank")

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

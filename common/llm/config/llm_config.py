# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

from enum import Enum
from typing import Optional, Dict, Any
from common.llm.config.config_reader import read_config_as_json


class LLMType(Enum):
    OPENAI_STYLE_LLM = "openai_style_llm"
    AOC_CHAT_LLM = "aoc_chat_llm"           # Chat model
    AOC_EMBEDDING_LLM = "aoc_embedding_llm" # Embedding model
    AOC_RERANKER_LLM = "aoc_reranker_llm"   # Reranker model


def convert_llm_type(llm_type: str) -> LLMType:
    for member in LLMType:
        if member.value == llm_type:
            return member
    # Default to OPENAI_STYLE_LLM; adjust as needed
    return LLMType.OPENAI_STYLE_LLM


class LLMConfigItem:
    description: str
    model: str
    api: str
    apikey: str
    enable_thinking: bool
    extra: Dict[str, Any]                       # New field

    def __init__(self, config: dict):
        self.description = config.get("description", "")
        self.model = config.get("model", "")
        self.api = config.get("api", "")
        self.apikey = config.get("api_key", "")
        self.enable_thinking = config.get("enable_thinking", True)
        self.extra = config.get("extra", {})    # New


class LLMConfig:
    llm_type: LLMType
    config_item: LLMConfigItem

    def __init__(self, llm_type: str, config_item: dict):
        self.llm_type = convert_llm_type(llm_type)
        self.config_item = LLMConfigItem(config_item)


def get_llm_config() -> dict[str, LLMConfig]:
    config: dict[str, dict] = read_config_as_json("../../../config/llm_config.json")
    llm_config_items = {}
    for key, config_item in config.items():
        llm_config_items[key] = LLMConfig(key, config_item)
    return llm_config_items


llm_config = get_llm_config()


def get_llm_config_by_type(llm_type: LLMType) -> Optional[LLMConfig]:
    if llm_type.value in llm_config:
        return llm_config[llm_type.value]
    return None
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

"""
LLM Module

This module provides a client wrapper for interacting with LLM API.
"""
from .llm import get_llm_instance
from .provider.aoc_chat_llm import AOCChatLLM
from .provider.aoc_embedding_llm import AOCEmbeddingLLM
from .provider.aoc_reranker_llm import AOCRerankerLLM
from .provider.llm_openai import OpenAIStyleLLM

__all__ = ["OpenAIStyleLLM",
           "get_llm_instance",
           "AOCRerankerLLM",
           "AOCEmbeddingLLM",
           "AOCChatLLM"
           ]
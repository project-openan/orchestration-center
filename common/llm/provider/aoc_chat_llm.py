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

import json
from typing import Dict, Any, Tuple

from loguru import logger

from common.llm.config.llm_config import LLMType, LLMConfig
from common.llm.provider.aoc_base_llm import AOCBaseLLM
from common.llm.provider.llm_provider_registry import registry_provider


@registry_provider(LLMType.AOC_CHAT_LLM)
class AOCChatLLM(AOCBaseLLM):
    """AOC chat model (e.g., Qwen3_32B)"""

    def __init__(self, llm_config: LLMConfig):
        super().__init__(llm_config)
        # Read custom template from extra, otherwise use default format
        extra = llm_config.config_item.extra
        self.request_template = extra.get('request_template')

    def _build_request_body(self, prompt: str) -> Dict[str, Any]:
        if self.request_template and isinstance(self.request_template, str):
            # Support template strings
            template_str = self.request_template.replace(
                '{prompt}', json.dumps(prompt)[1:-1]
            )
            template_str = template_str.replace(
                '{enable_thinking}', str(self.enable_thinking).lower()
            )
            return json.loads(template_str)
        else:
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
            if self.enable_thinking:
                body["chat_template_kwargs"] = {"enable_thinking": True}
            return body

    def _parse_response(self, data: Dict[str, Any]) -> Tuple[str, str]:
        # Standard OpenAI format parsing
        try:
            choice = data.get('choices', [{}])[0]
            message = choice.get('message', {})
            reasoning = message.get('reasoning_content', '') or ''
            answer = message.get('content', '') or ''
            if not answer:
                answer = data.get('text', '') or json.dumps(data, ensure_ascii=False)
            return reasoning, answer
        except Exception as e:
            logger.error(e)
            return '', json.dumps(data, ensure_ascii=False)
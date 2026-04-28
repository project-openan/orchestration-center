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
from typing import Dict, Any, Tuple, List

from common.llm.config.llm_config import LLMType, LLMConfig
from common.llm.provider.aoc_base_llm import AOCBaseLLM
from common.llm.provider.llm_provider_registry import registry_provider


@registry_provider(LLMType.AOC_EMBEDDING_LLM)
class AOCEmbeddingLLM(AOCBaseLLM):
    """AOC embedding model (e.g., bge_m3)"""

    def _build_request_body(self, prompt: str) -> Dict[str, Any]:
        # Default format: {"model": "...", "input": "..."}
        extra = self.llm_config.config_item.extra
        template = extra.get('request_template')
        if template and isinstance(template, str):
            template_str = template.replace('{prompt}', json.dumps(prompt)[1:-1])
            return json.loads(template_str)
        else:
            return {
                "model": self.model,
                "input": prompt
            }

    def _parse_response(self, data: Dict[str, Any]) -> Tuple[str, str]:
        # Convert vector to string for base class return
        vector = self._extract_embedding(data)
        return '', json.dumps(vector)

    def _extract_embedding(self, data: Dict[str, Any]) -> List[float]:
        """Extract embedding vector from response; subclasses can override for different response formats."""
        # Common format: {"data": [{"embedding": [...]}]}
        try:
            return data['data'][0]['embedding']
        except (KeyError, IndexError, TypeError):
            # Try other formats or raise an exception
            raise ValueError(f"Unable to extract embedding vector from response: {data}")

    def embed(self, prompt: str) -> List[float]:
        """
        Dedicated method for obtaining embedding vectors; returns a list of floats.
        """
        headers = self._build_headers()
        body = self._build_request_body(prompt)
        response = self.client.post(self.base_url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        return self._extract_embedding(data)

    # Override _ask_llm to call embed and return a string (compatible with base class)
    def _ask_llm(self, prompt: str) -> Tuple[str, str]:
        vector = self.embed(prompt)
        return '', json.dumps(vector)
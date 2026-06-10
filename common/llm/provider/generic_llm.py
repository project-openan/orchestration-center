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

import copy
import json
import time as _time
from typing import Any, Dict, List, Tuple, cast

import httpx
from loguru import logger

from common.llm.provider.auth_strategies import AUTH_STRATEGIES


class GenericLLM:
    def __init__(self, config: dict):
        self._url = config['url']
        self._model = config.get('model', '')
        self._api_key = config.get('api_key', '')
        self._enable_thinking = config.get('enable_thinking', False)
        self._body_template = config.get('body', {})
        self._response_paths = config.get('response', {})
        auth_cfg = config.get('auth')
        self._extra_headers = config.get('headers', {})
        self._description = config.get('description', '')

        if auth_cfg is None or auth_cfg == {}:
            self._auth_type = None
            self._auth_params = {}
        elif isinstance(auth_cfg, str):
            self._auth_type = auth_cfg
            self._auth_params = config.get('auth_params', {})
        else:
            self._auth_type = auth_cfg.get('type')
            self._auth_params = {k: v for k, v in auth_cfg.items() if k != 'type'}

        if self._auth_type and self._auth_type not in AUTH_STRATEGIES:
            raise ValueError(
                f"Unknown auth type '{self._auth_type}'. "
                f"Available: {list(AUTH_STRATEGIES.keys())}"
            )

        self._verify_ssl = config.get('verify_ssl', config.get('verify', True))
        self._client = httpx.Client(verify=self._verify_ssl, timeout=60.0)

    def to_dict(self):
        return {
            "name": self._description or self._model or "generic_llm"
        }

    # -- public API --

    def ask_llm(self, prompt: str) -> Tuple[str, str]:
        start = _time.time()
        try:
            body = self._render_body(prompt=prompt)
            data = self._do_request(body)
            answer = cast(str, self._extract(data, 'answer') or '')
            reasoning = cast(str, self._extract(data, 'reasoning') or '')
            duration = _time.time() - start
            logger.info(f"ask llm cost {duration:.2f}s")
            return reasoning, answer
        except Exception as e:
            logger.error(f"ask llm exception {e}")
            return '', ''

    def embed(self, prompt: str) -> List[float]:
        start = _time.time()
        try:
            body = self._render_body(prompt=prompt)
            data = self._do_request(body)
            result = self._extract(data, 'embedding')
            if result is None:
                raise ValueError(f"Unable to extract embedding from response: {data}")
            duration = _time.time() - start
            logger.info(f"embed cost {duration:.2f}s")
            return cast(List[float], result)
        except Exception as e:
            logger.error(f"embed exception {e}")
            return []

    def rerank(self, query: str, documents: List[str]) -> List[Dict[str, Any]]:
        start = _time.time()
        try:
            body = self._render_body(query=query, documents=documents)
            data = self._do_request(body)
            result = self._extract(data, 'results')
            if result is None:
                raise ValueError(f"Unable to parse reranker response: {data}")
            duration = _time.time() - start
            logger.info(f"rerank cost {duration:.2f}s")
            return cast(List[Dict[str, Any]], result)
        except Exception as e:
            logger.error(f"rerank exception {e}")
            return []

    # -- internal --

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}

        if self._auth_type:
            strategy = AUTH_STRATEGIES[self._auth_type]
            headers.update(strategy(self._auth_params))

        if self._api_key and 'Authorization' not in headers:
            headers['Authorization'] = f"Bearer {self._api_key}"

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        headers.update(self._extra_headers)
        return headers

    def _render_body(self, **runtime_vars) -> dict:
        vars_ctx = {
            'MODEL': self._model,
            'API_KEY': self._api_key,
            'ENABLE_THINKING': self._enable_thinking,
        }
        for k, v in runtime_vars.items():
            vars_ctx[k.upper()] = v
        return self._deep_replace(copy.deepcopy(self._body_template), vars_ctx)

    def _do_request(self, body: dict) -> dict:
        headers = self._build_headers()
        logger.debug(f"GenericLLM request: url={self._url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Body: {json.dumps(body, ensure_ascii=False)[:500]}")
        response = self._client.post(self._url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()

    def _extract(self, data: dict, key: str):
        path = self._response_paths.get(key)
        if path is None:
            return None
        current: Any = data
        for segment in path.replace('[', '.').replace(']', '').split('.'):
            if segment.isdigit():
                segment_int = int(segment)
                if isinstance(current, list) and segment_int < len(current):
                    current = current[segment_int]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(segment)
                if current is None:
                    return None
            else:
                return None
        return current

    @staticmethod
    def _deep_replace(obj: Any, vars_ctx: Dict[str, Any]) -> Any:
        if isinstance(obj, str):
            for var, val in vars_ctx.items():
                placeholder = f"${var}"
                if obj == placeholder:
                    return val
                if placeholder in obj:
                    if isinstance(val, (list, dict)):
                        val = json.dumps(val, ensure_ascii=False)
                    elif isinstance(val, bool):
                        val = str(val).lower()
                    else:
                        val = str(val)
                    obj = obj.replace(placeholder, val)
            return obj
        if isinstance(obj, dict):
            return {k: GenericLLM._deep_replace(v, vars_ctx) for k, v in obj.items()}
        if isinstance(obj, list):
            return [GenericLLM._deep_replace(item, vars_ctx) for item in obj]
        if isinstance(obj, bool):
            return obj
        return obj

    def __del__(self):
        if hasattr(self, '_client'):
            self._client.close()

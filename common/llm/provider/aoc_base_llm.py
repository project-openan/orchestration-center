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

import uuid
import hashlib
import base64
import random
import string
import time
from datetime import datetime
from abc import abstractmethod
from typing import Dict, Any, Tuple, Optional

import httpx
from loguru import logger

from common.llm.config.llm_config import LLMConfig
from common.llm.provider.base_llm import BaseLLM


class AOCBaseLLM(BaseLLM):
    """
    Base class for AOC platform signed requests, encapsulating common signing and HTTP logic.
    Subclasses must implement _build_request_body and _parse_response.
    """

    def __init__(self, llm_config: LLMConfig):
        super().__init__(llm_config)

        extra: Dict[str, Any] = self.llm_config.config_item.extra
        self.app_key = extra.get('app_key')
        self.app_secret = extra.get('app_secret')
        self.authorization = extra.get('authorization')
        self.scenario_code = extra.get('scenario_code', 'B99999999999')
        self.scenario_version = extra.get('scenario_version', 'V1')
        self.ability_code = extra.get('ability_code', 'A999999999')
        self.api_code = extra.get('api_code')
        self.api_version = extra.get('api_version', '1.0')
        self.test_flag = extra.get('test_flag', '1')

        missing = []
        if not self.app_key: missing.append('app_key')
        if not self.app_secret: missing.append('app_secret')
        if not self.authorization: missing.append('authorization')
        if not self.api_code: missing.append('api_code')
        if missing:
            raise ValueError(f"{self.__class__.__name__} missing required config: {', '.join(missing)}")

        self.client = httpx.Client(verify=False, timeout=60.0)

    # ------------------- Signature generation methods -------------------
    def _generate_message_id(self) -> str:
        return str(uuid.uuid4()).replace('-', '')

    def _generate_timestamp(self) -> str:
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d%H%M%S')
        millis = f"{now.microsecond // 1000:03d}"
        return timestamp + millis

    def _generate_md5_secret(self, message_id: str, timestamp: str) -> str:
        raw_str = f"{message_id}{self.app_secret}{timestamp}"
        md5_digest = hashlib.md5(raw_str.encode('utf-8')).digest()
        return base64.b64encode(md5_digest).decode('utf-8')

    def _generate_scenario_id(self) -> str:
        hex_time = format(int(time.time()), 'x')
        random_hex = ''.join(random.choices(string.hexdigits.lower(), k=24))
        return hex_time + random_hex

    def _generate_span_id(self) -> str:
        return ''.join(random.choices(string.hexdigits.lower(), k=16))

    def _build_headers(self) -> Dict[str, str]:
        message_id = self._generate_message_id()
        timestamp = self._generate_timestamp()
        md5_secret = self._generate_md5_secret(message_id, timestamp)

        return {
            'Content-Type': 'application/json',
            'Authorization': self.authorization,
            'x-sg-app-key': self.app_key,
            'x-sg-test': self.test_flag,
            'x-sg-message-id': message_id,
            'x-sg-timestamp': timestamp,
            'x-sg-md5-secret': md5_secret,
            'x-sg-scenario-code': self.scenario_code,
            'x-sg-scenario-version': self.scenario_version,
            'x-sg-ability-code': self.ability_code,
            'x-sg-api-code': self.api_code,
            'x-sg-api-version': self.api_version,
            'x-sg-scenario-id': self._generate_scenario_id(),
            'x-sg-spanid': self._generate_span_id(),
        }

    # ------------------- Abstract methods (subclasses must implement) -------------------
    @abstractmethod
    def _build_request_body(self, prompt: str) -> Dict[str, Any]:
        """Construct the request body; subclasses implement the specific model format."""
        pass

    @abstractmethod
    def _parse_response(self, data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Parse the response and return a (reasoning, answer) tuple.
        For non-chat models, reasoning can be an empty string.
        """
        pass

    # ------------------- Core invocation logic -------------------
    def _ask_llm(self, prompt: str) -> Tuple[str, str]:
        headers = self._build_headers()
        body = self._build_request_body(prompt)

        logger.debug(f"{self.__class__.__name__} Request URL: {self.base_url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Body: {body}")

        try:
            response = self.client.post(self.base_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"AOC API HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"AOC API request failed: {e}")
            raise

        return self._parse_response(data)

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()
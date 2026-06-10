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

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger


@dataclass
class ModelConfig:
    description: str = ""
    model: str = ""
    url: str = ""
    api_key: str = ""
    enable_thinking: bool = False
    auth: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_dict(key: str, raw: dict) -> "ModelConfig":
        return ModelConfig(
            description=raw.get("description", key),
            model=raw.get("model", ""),
            url=raw.get("url", ""),
            api_key=raw.get("api_key", ""),
            enable_thinking=raw.get("enable_thinking", False),
            auth=raw.get("auth"),
            headers=raw.get("headers", {}),
            body=raw.get("body", {}),
            response=raw.get("response", {}),
        )


_model_configs: Optional[Dict[str, ModelConfig]] = None


def _load_model_configs() -> Dict[str, ModelConfig]:
    global _model_configs
    if _model_configs is not None:
        return _model_configs

    try:
        from common.llm.config.config_reader import read_config_as_json
        raw_config = read_config_as_json("../../config/llm_config.json")
    except Exception as e:
        logger.error(f"Failed to load LLM config: {e}")
        raw_config = {}

    _model_configs = {
        key: ModelConfig.from_dict(key, val)
        for key, val in raw_config.items()
    }
    return _model_configs


def get_model_config(capability: str) -> Optional[ModelConfig]:
    return _load_model_configs().get(capability)

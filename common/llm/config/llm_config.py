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

@dataclass
class ModelConfig:
    description: str = ""
    model: str = ""
    url: str = ""
    api_key: str = ""
    enable_thinking: bool = False
    verify_ssl: bool = True
    timeout: float = 60.0
    auth: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, str] = field(default_factory=dict)
    stream: bool = False
    proxy: str = ""
    stream_total_timeout: float = 600.0
    input_modalities: tuple[str, ...] = ("text",)

    @staticmethod
    def from_dict(key: str, raw: dict) -> "ModelConfig":
        return ModelConfig(
            description=raw.get("description", key),
            model=raw.get("model", ""),
            url=raw.get("url", ""),
            api_key=raw.get("api_key", ""),
            enable_thinking=raw.get("enable_thinking", False),
            verify_ssl=raw.get("verify_ssl", True),
            timeout=float(raw.get("timeout", 60.0)),
            auth=raw.get("auth"),
            headers=raw.get("headers", {}),
            body=raw.get("body", {}),
            response=raw.get("response", {}),
            stream=bool(raw.get("stream", False)),
            proxy=raw.get("proxy", ""),
            stream_total_timeout=float(raw.get("stream_total_timeout", 600.0)),
            input_modalities=tuple(raw.get("input_modalities", ("text",))),
        )

class _ModelConfigHolder:
    """Lazy holder for model configurations (avoids mutable global state)."""
    _instance: Optional[Dict[str, ModelConfig]] = None

    @classmethod
    def get(cls) -> Dict[str, ModelConfig]:
        if cls._instance is None:
            cls._instance = cls._load()
        return cls._instance

    @classmethod
    def _load(cls) -> Dict[str, ModelConfig]:
        from common.llm.config.model_sources import load_model_configs
        return {
            key: ModelConfig.from_dict(key, value)
            for key, value in load_model_configs().items()
        }

    @classmethod
    def reset(cls) -> None:
        """Drop the cached configuration. Intended for tests."""
        cls._instance = None

def get_model_config(capability: str) -> Optional[ModelConfig]:
    return _ModelConfigHolder.get().get(capability)

REQUIRED_FIELDS = ("url", "model")

def is_placeholder(value: str) -> bool:
    value = (value or "").strip()
    return not value or (value.startswith("<") and value.endswith(">"))

def missing_required_fields(config: ModelConfig) -> list:
    return [field for field in REQUIRED_FIELDS if is_placeholder(getattr(config, field, ""))]

def describe_missing_fields(capability: str, missing: list) -> str:
    return (
        f"LLM capability '{capability}' is not configured: {', '.join(missing)}. "
        "Set model and url in etc/config/models.yaml (or LLM_CONFIG_FILE)."
    )

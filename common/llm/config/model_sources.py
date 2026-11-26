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

"""Model definitions from YAML; credentials from explicitly named environment keys."""

from __future__ import annotations

import copy
import math
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_FILE = ROOT / "etc" / "config" / "models.yaml"
# Pre-migration deployments may still keep the model file under common/config;
# it is honored when etc/config/models.yaml does not exist.
LEGACY_MODEL_FILE = ROOT / "common" / "config" / "models.yaml"
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
MODEL_FIELDS = {
    "provider", "description", "model", "url", "api_key_env",
    "enable_thinking", "verify_ssl", "timeout", "auth",
    "stream", "proxy", "stream_total_timeout", "extra_body",
}
AUTH_PUBLIC_FIELDS = {
    "api_code", "api_version", "scenario_code", "scenario_version",
    "ability_code", "test_flag",
}


class SettingsSource(Protocol):
    def get(self, name: str) -> str | None: ...


class EnvironmentSettingsSource:
    """Read only named secrets and the config path; process environment wins."""

    def __init__(self, dotenv_path: Path | None = None) -> None:
        path = dotenv_path or ROOT / ".env"
        self._dotenv = dotenv_values(path) if path.is_file() else {}

    def get(self, name: str) -> str | None:
        value = os.environ.get(name)
        if not isinstance(value, str) or not value.strip():
            value = self._dotenv.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None


ProfileFactory = Callable[[str, Callable[[str], str | None]], dict[str, Any]]
_PROFILES: dict[tuple[str, str], ProfileFactory] = {}


def register_profile(provider: str, capability: str, factory: ProfileFactory) -> None:
    """Register a protocol contract without changing the YAML loader."""
    key = (provider.lower(), capability.lower())
    if key in _PROFILES:
        raise ValueError(f"Duplicate model profile: {provider}/{capability}")
    _PROFILES[key] = factory


def build_profile(
    provider: str, capability: str, get: Callable[[str], str | None],
) -> dict[str, Any]:
    factory = _PROFILES.get((provider.lower(), capability.lower()))
    if factory is None:
        raise ValueError(f"No model profile for {provider}/{capability}")
    return factory(capability, get)


def _standard_profile(capability: str, _get: Callable[[str], str | None]) -> dict[str, Any]:
    contracts = {
        "chat": (
            {"model": "$MODEL", "messages": [{"role": "user", "content": "$PROMPT"}]},
            {"answer": "choices[0].message.content", "reasoning": "choices[0].message.reasoning_content"},
        ),
        "embed": (
            {"model": "$MODEL", "input": "$PROMPT"},
            {"embedding": "data[0].embedding"},
        ),
        "rerank": (
            {"model": "$MODEL", "query": "$QUERY", "documents": "$DOCUMENTS"},
            {"results": "results"},
        ),
    }
    body, response = contracts[capability]
    return {"body": copy.deepcopy(body), "response": dict(response), "auth": None, "headers": {}}


_AOC_FIELDS = (
    "app_key", "app_secret", "authorization", "api_code", "api_version",
    "scenario_code", "scenario_version", "ability_code", "test_flag",
)


def _aoc_profile(capability: str, get: Callable[[str], str | None]) -> dict[str, Any]:
    config = _standard_profile(capability, get)
    auth = {field: get(field) for field in _AOC_FIELDS}
    if not auth["app_key"] or not auth["app_secret"]:
        raise ValueError(f"{capability}: AOC profile requires auth.app_key_env and auth.app_secret_env")
    config["auth"] = {"type": "aoc_signed", **{k: v for k, v in auth.items() if v is not None}}
    return config


for _capability in ("chat", "embed", "rerank"):
    register_profile("openai_compatible", _capability, _standard_profile)
    register_profile("openai", _capability, _standard_profile)
    register_profile("aoc_signed", _capability, _aoc_profile)


def _secret(source: SettingsSource, name: Any, location: str) -> str:
    if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
        raise ValueError(f"{location} must name an environment variable")
    value = source.get(name)
    if value is None:
        raise ValueError(f"{location}: environment variable {name} is not set")
    return value


def _auth_values(raw: Any, source: SettingsSource, location: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{location} must be a mapping")
    values: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not CAPABILITY_NAME.fullmatch(key):
            raise ValueError(f"{location} has an invalid field name")
        if key.endswith("_env"):
            field = key[:-4]
            if field in raw:
                raise ValueError(f"{location}.{field} and {key} are mutually exclusive")
            values[field] = _secret(source, value, f"{location}.{key}")
        else:
            if key not in AUTH_PUBLIC_FIELDS:
                raise ValueError(f"{location}.{key} must use {key}_env")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"{location}.{key} must be a scalar")
            values[key] = str(value)
    return values


def resolve_model_file(source: SettingsSource | None = None) -> Path:
    source = source or EnvironmentSettingsSource()
    selected = source.get("LLM_CONFIG_FILE")
    if selected:
        path = Path(selected)
        return path if path.is_absolute() else ROOT / path
    if DEFAULT_MODEL_FILE.is_file():
        return DEFAULT_MODEL_FILE
    return LEGACY_MODEL_FILE


def load_model_configs(
    source: SettingsSource | None = None, path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load one authoritative model file; never merge scalar values from env."""
    source = source or EnvironmentSettingsSource()
    selected = path or resolve_model_file(source)
    if not selected.is_file():
        if path is not None or source.get("LLM_CONFIG_FILE"):
            raise FileNotFoundError(f"Model configuration file not found: {selected}")
        return {}
    document = yaml.safe_load(selected.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"models"}:
        raise ValueError(f"{selected}: expected a single 'models' mapping")
    models = document["models"]
    if not isinstance(models, dict):
        raise ValueError(f"{selected}: 'models' must be a mapping")
    result: dict[str, dict[str, Any]] = {}
    for capability, raw in models.items():
        if not isinstance(capability, str) or not CAPABILITY_NAME.fullmatch(capability):
            raise ValueError(f"{selected}: invalid capability name")
        if not isinstance(raw, dict):
            raise ValueError(f"{selected}: {capability} must be a mapping")
        unknown = set(raw) - MODEL_FIELDS
        if unknown:
            raise ValueError(f"{selected}: {capability} has unsupported fields: {', '.join(sorted(map(str, unknown)))}")
        model, url = raw.get("model"), raw.get("url")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"{selected}: {capability}.model is required")
        if not isinstance(url, str):
            raise ValueError(f"{selected}: {capability}.url is required")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError(f"{selected}: {capability}.url must be an HTTP(S) URL without embedded credentials")
        provider = raw.get("provider", "openai_compatible")
        if not isinstance(provider, str) or not provider:
            raise ValueError(f"{selected}: {capability}.provider must be a string")
        auth = _auth_values(raw.get("auth"), source, f"{capability}.auth")
        accessed_auth: set[str] = set()
        def get_auth(field: str) -> str | None:
            accessed_auth.add(field)
            return auth.get(field)
        config = build_profile(provider, capability, get_auth)
        # Profiles may apply auth to headers rather than return an auth block.
        # Reject settings the selected profile never even reads.
        if auth and not accessed_auth:
            raise ValueError(
                f"{selected}: {capability}.auth is not supported by provider '{provider}'"
            )
        unused_auth = set(auth) - accessed_auth
        if unused_auth:
            raise ValueError(f"{selected}: {capability}.auth has unused fields: {', '.join(sorted(unused_auth))}")
        timeout = raw.get("timeout", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"{selected}: {capability}.timeout must be positive")
        stream_total_timeout = raw.get("stream_total_timeout", 600)
        if isinstance(stream_total_timeout, bool) or not isinstance(stream_total_timeout, (int, float)) \
                or not math.isfinite(stream_total_timeout) or stream_total_timeout <= 0:
            raise ValueError(f"{selected}: {capability}.stream_total_timeout must be positive")
        if "proxy" in raw and not isinstance(raw["proxy"], str):
            raise ValueError(f"{selected}: {capability}.proxy must be a string")
        if "extra_body" in raw and not isinstance(raw["extra_body"], dict):
            raise ValueError(f"{selected}: {capability}.extra_body must be a mapping")
        for key in ("verify_ssl", "enable_thinking", "stream"):
            if key in raw and not isinstance(raw[key], bool):
                raise ValueError(f"{selected}: {capability}.{key} must be boolean")
        description = raw.get("description", capability)
        if not isinstance(description, str):
            raise ValueError(f"{selected}: {capability}.description must be a string")
        api_key = _secret(source, raw["api_key_env"], f"{capability}.api_key_env") if "api_key_env" in raw else ""
        config.update({
            "description": description, "model": model, "url": url, "api_key": api_key,
            "timeout": float(timeout), "verify_ssl": raw.get("verify_ssl", True),
            "enable_thinking": raw.get("enable_thinking", False),
            "stream": raw.get("stream", False),
            "proxy": raw.get("proxy", ""),
            "stream_total_timeout": float(stream_total_timeout),
        })
        if config['stream'] and not config.get('response', {}).get('answer'):
            raise ValueError(f"{selected}: {capability} does not support chat streaming")
        # Provider options may extend, never replace, the protocol inputs.
        if raw.get("extra_body"):
            reserved = set(config.get('body', {})) | {'model', 'messages', 'input', 'query', 'documents', 'stream'}
            overlap = reserved.intersection(raw['extra_body'])
            if overlap:
                raise ValueError(f"{selected}: {capability}.extra_body overrides reserved fields: {', '.join(sorted(overlap))}")
            config["body"] = {**config.get("body", {}), **raw["extra_body"]}
        result[capability] = config
    return result

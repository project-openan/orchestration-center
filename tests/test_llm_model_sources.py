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

"""YAML model definitions, secret references, and migration boundaries."""

import os
import stat
import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from common.llm.config.llm_config import get_model_config
from common.llm.config.model_sources import (
    EnvironmentSettingsSource, build_profile, load_model_configs, register_profile,
)
from common.llm.config import model_sources as model_sources_mod
from common.llm.llm import get_llm_instance, reset_instances
from common.llm.provider.generic_llm import GenericLLM
from scripts.migrate_llm_config import migrate
from scripts.migrate_legacy_llm_json import migrate as migrate_legacy


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_CONFIG_FILE", str(tmp_path / "models.yaml"))
    monkeypatch.setattr(
        "common.llm.config.model_sources.EnvironmentSettingsSource",
        lambda: EnvironmentSettingsSource(tmp_path / ".env"),
    )
    reset_instances()
    yield
    reset_instances()


def write_models(tmp_path, models):
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"models": models}), encoding="utf-8")
    return path


def chat(**options):
    return {"model": "chat-model", "url": "https://example.invalid/chat", **options}


@pytest.mark.parametrize("provider", [None, "openai_compatible", "openai"])
def test_openai_compatible_profile_and_legacy_alias(tmp_path, provider):
    definition = chat()
    if provider is not None:
        definition["provider"] = provider
    write_models(tmp_path, {"chat": definition})
    assert get_model_config("chat").body["messages"][0]["content"] == "$PROMPT"


def test_environment_only_resolves_named_secret(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("CHAT_SECRET=file-secret\n", encoding="utf-8")
    write_models(tmp_path, {"chat": chat(api_key_env="CHAT_SECRET")})
    assert get_model_config("chat").api_key == "file-secret"
    reset_instances()
    monkeypatch.setenv("CHAT_SECRET", "process-secret")
    assert get_model_config("chat").api_key == "process-secret"


def test_model_definition_comes_only_from_yaml(monkeypatch, tmp_path):
    write_models(tmp_path, {"chat": chat()})
    monkeypatch.setenv("LLM_CHAT_MODEL", "ignored-model")
    monkeypatch.setenv("LLM_CHAT_URL", "https://ignored.invalid")
    config = get_model_config("chat")
    assert config.model == "chat-model"
    assert config.url == "https://example.invalid/chat"


def test_stream_proxy_and_extra_body_pass_through(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAT_KEY", "secret")
    write_models(tmp_path, {"chat": chat(
        api_key_env="CHAT_KEY",
        stream=True,
        proxy="socks5://127.0.0.1:7897",
        stream_total_timeout=480,
        extra_body={"effort": "low", "max_tokens": 65536},
    )})
    config = load_model_configs()["chat"]
    assert config["stream"] is True
    assert config["proxy"] == "socks5://127.0.0.1:7897"
    assert config["stream_total_timeout"] == 480.0
    # extra_body merges on top of the profile contract, never replaces it
    assert config["body"]["effort"] == "low"
    assert config["body"]["max_tokens"] == 65536
    assert config["body"]["messages"] == [{"role": "user", "content": "$PROMPT"}]
    assert config["body"]["model"] == "$MODEL"


def test_stream_proxy_defaults_when_absent(tmp_path):
    write_models(tmp_path, {"chat": chat()})
    config = load_model_configs()["chat"]
    assert config["stream"] is False
    assert config["proxy"] == ""
    assert config["stream_total_timeout"] == 600.0


def test_invalid_stream_total_timeout_rejected(tmp_path):
    write_models(tmp_path, {"chat": chat(stream_total_timeout=-5)})
    with pytest.raises(ValueError, match="stream_total_timeout"):
        load_model_configs()


def test_invalid_extra_body_rejected(tmp_path):
    write_models(tmp_path, {"chat": chat(extra_body="not-a-mapping")})
    with pytest.raises(ValueError, match="extra_body"):
        load_model_configs()


def test_generic_llm_picks_up_stream_and_proxy(tmp_path):
    # http proxy on purpose: constructing the client must not require the
    # optional socksio dependency that socks5:// proxies would pull in.
    write_models(tmp_path, {"chat": chat(
        stream=True,
        proxy="http://127.0.0.1:7897",
        stream_total_timeout=480,
    )})
    instance = get_llm_instance()
    assert instance._stream is True
    assert instance._proxy == "http://127.0.0.1:7897"
    assert instance._stream_total_timeout == 480.0
    assert get_model_config("embed") is None


def test_keyless_local_model(tmp_path):
    write_models(tmp_path, {"chat": chat(url="http://127.0.0.1:8000/v1/chat/completions")})
    assert get_llm_instance()._api_key == ""


def test_aoc_profile_resolves_only_explicit_secret_refs(tmp_path):
    (tmp_path / ".env").write_text("AOC_KEY=app\nAOC_SECRET=secret\n", encoding="utf-8")
    write_models(tmp_path, {"chat": chat(provider="aoc_signed", auth={
        "app_key_env": "AOC_KEY", "app_secret_env": "AOC_SECRET", "api_code": "code",
    })})
    assert get_model_config("chat").auth == {
        "type": "aoc_signed", "app_key": "app", "app_secret": "secret", "api_code": "code",
    }


def test_missing_secret_fails_without_exposing_value(tmp_path):
    path = write_models(tmp_path, {"chat": chat(api_key_env="MISSING_SECRET")})
    with pytest.raises(ValueError, match="MISSING_SECRET"):
        load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)


@pytest.mark.parametrize("model,match", [
    (chat(api_key="inline-secret"), "unsupported fields"),
    (chat(provider="aoc_signed", auth={"app_key": "inline-secret"}), "must use app_key_env"),
    (chat(timeout=0), "timeout"),
    (chat(verify_ssl="false"), "verify_ssl"),
    (chat(url="https://user:pass@example.invalid"), "embedded credentials"),
    (chat(api_key_env="BAD-NAME"), "environment variable"),
])
def test_invalid_or_inline_secret_configuration_fails(tmp_path, model, match):
    path = write_models(tmp_path, {"chat": model})
    with pytest.raises(ValueError, match=match):
        load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)


def test_explicit_missing_file_fails(tmp_path):
    with pytest.raises(FileNotFoundError, match="models.yaml"):
        load_model_configs()


def test_new_profile_registration_needs_no_loader_edit(tmp_path):
    register_profile("test_profile", "vision", lambda capability, get: {
        "body": {"model": "$MODEL", "image": "$PROMPT"},
        "response": {"answer": "result"}, "auth": None, "headers": {},
    })
    path = write_models(tmp_path, {"vision": {
        "provider": "test_profile", "model": "v1", "url": "https://example.invalid/vision",
    }})
    assert load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)["vision"]["body"]["image"] == "$PROMPT"


def test_openai_profile_rejects_unconsumed_auth(tmp_path):
    path = write_models(tmp_path, {"chat": chat(auth={"api_code": "unused"})})
    with pytest.raises(ValueError, match="not supported"):
        load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)


def test_custom_profile_can_consume_auth_as_headers(tmp_path):
    (tmp_path / ".env").write_text("TENANT=example\n", encoding="utf-8")
    register_profile("header_profile", "vision", lambda capability, get: {
        "body": {"image": "$PROMPT"}, "response": {"answer": "result"},
        "auth": None, "headers": {"X-Tenant": get("tenant")},
    })
    path = write_models(tmp_path, {"vision": {
        "provider": "header_profile", "model": "v1",
        "url": "https://example.invalid/vision", "auth": {"tenant_env": "TENANT"},
    }})
    result = load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)
    assert result["vision"]["headers"]["X-Tenant"] == "example"


def test_unused_auth_field_is_rejected(tmp_path):
    (tmp_path / ".env").write_text("AOC_KEY=app\nAOC_SECRET=secret\nTYPO=unused\n", encoding="utf-8")
    path = write_models(tmp_path, {"chat": chat(provider="aoc_signed", auth={
        "app_key_env": "AOC_KEY", "app_secret_env": "AOC_SECRET", "typo_env": "TYPO",
    })})
    with pytest.raises(ValueError, match="unused fields: typo"):
        load_model_configs(EnvironmentSettingsSource(tmp_path / ".env"), path)


def test_request_debug_log_omits_secret_and_prompt():
    client = GenericLLM({
        "url": "https://example.invalid/chat", "model": "m", "api_key": "secret-key",
        "body": {"prompt": "$PROMPT"}, "response": {},
    })
    client._client = MagicMock()
    client._client.post.return_value.json.return_value = {}
    with patch("common.llm.provider.generic_llm.logger") as log:
        client._do_request({"prompt": "private-user-prompt"})
    messages = " ".join(str(call) for call in log.debug.call_args_list)
    assert "secret-key" not in messages
    assert "private-user-prompt" not in messages


def test_migration_moves_only_non_secret_values(tmp_path):
    dotenv = tmp_path / ".env"
    models = tmp_path / "models.yaml"
    dotenv.write_text(
        "A2AT_LLM_MODEL=keep-this\nLLM_CAPABILITIES=chat\n"
        "LLM_CHAT_PROVIDER=openai\nLLM_CHAT_MODEL=m\n"
        "LLM_CHAT_URL=https://example.invalid\nLLM_CHAT_API_KEY=secret-value\n",
        encoding="utf-8",
    )
    assert migrate(dotenv, models) == ["chat"]
    assert yaml.safe_load(models.read_text(encoding="utf-8"))["models"]["chat"]["api_key_env"] == "LLM_CHAT_API_KEY"
    assert "secret-value" not in models.read_text(encoding="utf-8")
    content = dotenv.read_text(encoding="utf-8")
    assert "A2AT_LLM_MODEL=keep-this" in content
    assert "LLM_CHAT_API_KEY=secret-value" in content
    assert "LLM_CHAT_MODEL" not in content


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode")
def test_migration_keeps_secrets_private_and_model_file_shareable(tmp_path):
    dotenv = tmp_path / ".env"
    models = tmp_path / "models.yaml"
    dotenv.write_text("LLM_CHAT_MODEL=m\nLLM_CHAT_URL=https://example.invalid\n", encoding="utf-8")
    migrate(dotenv, models)
    assert stat.S_IMODE(dotenv.stat().st_mode) == 0o600
    assert stat.S_IMODE(models.stat().st_mode) == 0o644


def test_migration_rejects_existing_model_conflict(tmp_path):
    dotenv = tmp_path / ".env"
    models = write_models(tmp_path, {"chat": chat()})
    dotenv.write_text("LLM_CHAT_MODEL=other\nLLM_CHAT_URL=https://example.invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Existing model file differs"):
        migrate(dotenv, models)
    assert "LLM_CHAT_MODEL=other" in dotenv.read_text(encoding="utf-8")


def test_migration_rejects_invalid_setting_without_writing(tmp_path):
    dotenv = tmp_path / ".env"
    models = tmp_path / "models.yaml"
    dotenv.write_text(
        "LLM_CHAT_MODEL=m\nLLM_CHAT_URL=https://example.invalid\nLLM_CHAT_TIMEOUT=-1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timeout"):
        migrate(dotenv, models)
    assert not models.exists()


def test_legacy_json_migrates_directly_without_inline_secrets(tmp_path):
    source, dotenv, models = tmp_path / "old.json", tmp_path / ".env", tmp_path / "models.yaml"
    profile = build_profile("openai", "chat", lambda _: None)
    source.write_text(json.dumps({"chat": {
        **profile, "model": "m", "url": "https://example.invalid",
        "api_key": "secret-value",
    }}), encoding="utf-8")
    dotenv.write_text("A2AT_LLM_MODEL=keep-this\n", encoding="utf-8")
    assert migrate_legacy(source, dotenv, models) == ["chat"]
    assert "secret-value" not in models.read_text(encoding="utf-8")
    assert "A2AT_LLM_MODEL=keep-this" in dotenv.read_text(encoding="utf-8")
    assert load_model_configs(EnvironmentSettingsSource(dotenv), models)["chat"]["api_key"] == "secret-value"


def test_legacy_json_rejects_custom_protocol_before_writing(tmp_path):
    source, dotenv, models = tmp_path / "old.json", tmp_path / ".env", tmp_path / "models.yaml"
    source.write_text(json.dumps({"chat": {
        "model": "m", "url": "https://example.invalid",
        "body": {"custom": "$PROMPT"},
    }}), encoding="utf-8")
    with pytest.raises(ValueError, match="custom body template"):
        migrate_legacy(source, dotenv, models)
    assert not dotenv.exists() and not models.exists()


class _StaticSource:
    """Minimal SettingsSource isolated from the autouse test fixture."""

    def __init__(self, values):
        self._values = dict(values)

    def get(self, name):
        return self._values.get(name)

class _StaticSource:
    """Minimal SettingsSource isolated from the autouse test fixture."""

    def __init__(self, values):
        self._values = dict(values)

    def get(self, name):
        return self._values.get(name)


def test_etc_config_models_yaml_takes_precedence_over_legacy(tmp_path, monkeypatch):
    """The etc/config location wins; the legacy common/config file is only a fallback."""
    etc_file = tmp_path / "etc" / "config" / "models.yaml"
    legacy_file = tmp_path / "common" / "config" / "models.yaml"
    etc_file.parent.mkdir(parents=True)
    legacy_file.parent.mkdir(parents=True)
    etc_payload = (
        "models:\n"
        "  chat:\n"
        "    model: from-etc\n"
        "    url: https://example.invalid/chat\n"
        "    api_key_env: LLM_CHAT_API_KEY\n"
    )
    legacy_payload = (
        "models:\n"
        "  chat:\n"
        "    model: from-legacy\n"
        "    url: https://example.invalid/chat\n"
        "    api_key_env: LLM_CHAT_API_KEY\n"
    )
    etc_file.write_text(etc_payload, encoding="utf-8")
    legacy_file.write_text(legacy_payload, encoding="utf-8")
    source = _StaticSource({"LLM_CHAT_API_KEY": "secret-value"})
    monkeypatch.delenv("LLM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(model_sources_mod, "DEFAULT_MODEL_FILE", etc_file)
    monkeypatch.setattr(model_sources_mod, "LEGACY_MODEL_FILE", legacy_file)

    assert model_sources_mod.resolve_model_file(source) == etc_file
    configs = model_sources_mod.load_model_configs(source)
    assert configs["chat"]["model"] == "from-etc"


def test_legacy_common_config_models_yaml_still_supported(tmp_path, monkeypatch):
    """Pre-migration deployments with only common/config/models.yaml keep working."""
    legacy_file = tmp_path / "common" / "config" / "models.yaml"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text(
        "models:\n"
        "  chat:\n"
        "    model: from-legacy\n"
        "    url: https://example.invalid/chat\n"
        "    api_key_env: LLM_CHAT_API_KEY\n",
        encoding="utf-8",
    )
    source = _StaticSource({"LLM_CHAT_API_KEY": "secret-value"})
    monkeypatch.delenv("LLM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(model_sources_mod, "DEFAULT_MODEL_FILE", tmp_path / "etc" / "config" / "models.yaml")
    monkeypatch.setattr(model_sources_mod, "LEGACY_MODEL_FILE", legacy_file)

    assert model_sources_mod.resolve_model_file(source) == legacy_file
    configs = model_sources_mod.load_model_configs(source)
    assert configs["chat"]["model"] == "from-legacy"


@pytest.mark.parametrize('key', ['model', 'messages', 'input', 'query', 'documents', 'stream'])
def test_extra_body_cannot_replace_protocol_inputs(tmp_path, key):
    path = write_models(tmp_path, {'chat': chat(extra_body={key: 'override'})})
    with pytest.raises(ValueError, match='reserved fields'):
        load_model_configs(EnvironmentSettingsSource(tmp_path/'.env'), path)


@pytest.mark.parametrize('capability', ['embed', 'rerank'])
def test_non_chat_capabilities_reject_stream(tmp_path, capability):
    path = write_models(tmp_path, {capability: chat(stream=True)})
    with pytest.raises(ValueError, match='does not support chat streaming'):
        load_model_configs(EnvironmentSettingsSource(tmp_path/'.env'), path)

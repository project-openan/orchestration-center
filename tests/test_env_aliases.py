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

"""Deployment aliases must cover every security-relevant configuration key.

Container and chart deployments inject configuration as environment
variables, not files: a key without an alias is one that those deployments
silently cannot set. This pins the security-related half of the alias table
so a new key cannot regress into env-uninjectable again.
"""

from common.util.config_util import apply_env_overrides


def test_all_retrieval_environment_aliases_override_file_settings(monkeypatch):
    values = {"ENABLED": "true", "TOP_K": "7", "MIN_SCORE": "0.25", "RERANK": "true",
              "LLM_FINAL": "false", "STRICT": "true", "INDEX_FILE": "data/custom/index.json"}
    config = {"retrieval.vector.enabled": "false"}
    for suffix, value in values.items():
        monkeypatch.setenv("RETRIEVAL_VECTOR_" + suffix, value)
    monkeypatch.setenv("RETRIEVAL_LLM_THINKING", "false")
    apply_env_overrides(config)
    from orchestrate.core.psop_vector_index import VectorSettings
    settings = VectorSettings.from_config(config)
    assert settings.enabled and settings.rerank and settings.strict
    assert settings.top_k == 7 and settings.min_score == 0.25
    assert not settings.llm_final and not settings.thinking
    assert settings.index_file == "data/custom/index.json"


def test_get_conf_retrieval_environment_has_highest_precedence(tmp_path, monkeypatch):
    from common.util import config_util
    conf = tmp_path / "etc/conf"
    conf.mkdir(parents=True)
    (conf / "server.conf").write_text("retrieval.vector.top_k=2\n")
    (conf / "server.properties").write_text("retrieval.vector.top_k=3\n")
    monkeypatch.setattr(config_util, "get_root_path", lambda: str(tmp_path))
    monkeypatch.setenv("RETRIEVAL_VECTOR_TOP_K", "7")
    config_util.get_conf.cache_clear()
    try:
        assert config_util.get_conf()["retrieval.vector.top_k"] == "7"
    finally:
        config_util.get_conf.cache_clear()


def test_security_keys_have_env_aliases(monkeypatch):
    monkeypatch.setenv("ORCH_SSL_CRL_FILE", "etc/ssl/revocationlist.crl")
    monkeypatch.setenv("ORCH_ACCESS_TOKEN_TTL", "3600")
    monkeypatch.setenv("ORCH_EXTERNAL_AUTH_TOKEN_ENV", "MY_API_TOKEN_ENV")
    monkeypatch.setenv("REGISTRY_CLIENT_KEY_PASSWORD_ENV", "MY_KEY_PASSWORD_ENV")
    config = {}
    apply_env_overrides(config)
    assert config["ssl_crl_file"] == "etc/ssl/revocationlist.crl"
    assert config["access_token_ttl"] == "3600"
    assert config["external.auth.token_env"] == "MY_API_TOKEN_ENV"
    assert config["agent_registry.client_key_password_env"] == "MY_KEY_PASSWORD_ENV"


def test_existing_transport_aliases_still_resolve(monkeypatch):
    monkeypatch.setenv("ORCH_ENABLE_HTTPS", "true")
    monkeypatch.setenv("ORCH_CLIENT_VERIFY_SERVER", "true")
    config = {}
    apply_env_overrides(config)
    assert config["enable_https"] == "true"
    assert config["client_verify_server"] == "true"


def test_removed_dev_alias_cannot_add_an_authentication_switch(monkeypatch):
    monkeypatch.setenv("ORCH_DEV_INSECURE_MODE", "true")
    config = {}
    apply_env_overrides(config)
    assert "security.dev_insecure_mode" not in config

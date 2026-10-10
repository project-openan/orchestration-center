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

import os
from functools import lru_cache

from loguru import logger


def get_root_path():
    current_script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(current_script_path)
    root_path = os.path.dirname(os.path.dirname(script_dir))
    return root_path


@lru_cache(maxsize=1)
def get_conf():
    config = {}
    root_path = get_root_path()
    base_config_path = os.path.join(root_path, "etc", "conf","server.conf")
    save_config_path = os.path.join(root_path, "etc", "conf","server.properties")
    load_configs(base_config_path, config)
    load_configs(save_config_path, config)
    apply_env_overrides(config)
    return config


def apply_env_overrides(config: dict) -> None:
    """Explicit deployment aliases; never materialize credentials into files."""
    aliases = {
        "ORCH_IP": "ip", "ORCH_PORT": "port", "ORCH_ENABLE_HTTPS": "enable_https",
        "ORCH_VERIFY_CLIENT": "verify_client", "ORCH_CLIENT_VERIFY_SERVER": "client_verify_server",
        "ORCH_FORWARDED_ALLOW_IPS": "forwarded_allow_ips", "ORCH_PUBLIC_SCHEME": "public_scheme",
        "ORCH_ACCESS_PASSWORD": "access_password", "ORCH_EXTERNAL_AUTH_MODE": "external.auth.mode",
        "ORCH_SSL_CERTFILE": "ssl_certfile", "ORCH_SSL_KEYFILE": "ssl_keyfile",
        "ORCH_SSL_KEYFILE_PASSWORD": "ssl_keyfile_password", "ORCH_SSL_CA_CERTS": "ssl_ca_certs",
        "REGISTRY_CA_FILE": "agent_registry.ca_file", "REGISTRY_CLIENT_CERT": "agent_registry.client_cert",
        "REGISTRY_CLIENT_KEY": "agent_registry.client_key",
        "AGENT_REGISTRY_URL": "agent_registry_url", "PERSISTENCE_MODE": "persistence_mode",
    }
    for name, key in aliases.items():
        if name in os.environ:
            config[key] = os.environ[name]
    if os.environ.get("PORT"):
        config["port"] = os.environ["PORT"]
    config["forwarded_allow_ips"] = str(config.get("forwarded_allow_ips", "127.0.0.1")).strip('"\'')


def load_configs(config_path, config):
    if not os.path.exists(config_path):
        logger.error(f"Error:The configuration file {config_path} does not exist")
        return
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if '#' in line:
                line = line[:line.index('#')].strip()
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                config[key.lower()] = value
            else:
                logger.warning(f"Skipping line without '=': {line}")

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

from common.util.config_util import get_conf
from orchestrate.registry_client.client import AgentRegistryClient


class AgentRegistryClientFactory:
    """Create an AgentRegistryClient instance based on the configuration"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.default_base_url = get_conf().get("agent_registry_url", "http://127.0.0.1:5000")

    def create_client(self, base_url: str = None, timeout: int = 30) -> AgentRegistryClient:
        url = base_url or self.default_base_url
        timeout_seconds = timeout or self.config.get("timeout", 30)
        verify_server = str(
            self.config.get(
                "ssl_verify",
                get_conf().get("client_verify_server", "true"),
            )
        ).lower() == "true"
        conf = {**get_conf(), **self.config}
        token_name = str(conf.get("agent_registry.token_env", "REGISTRY_ACCESS_TOKEN"))
        token = os.environ.get(token_name, "") if token_name else ""
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        options = {}
        for key, argument in (("agent_registry.ca_file", "ca_certs_path"),
                              ("agent_registry.client_cert", "cert_path"),
                              ("agent_registry.client_key", "key_path")):
            if conf.get(key):
                options[argument] = conf[key]
        password_name = str(conf.get("agent_registry.client_key_password_env", "REGISTRY_CLIENT_KEY_PASSWORD"))
        if password_name and os.environ.get(password_name):
            options["key_password"] = os.environ[password_name]
        return AgentRegistryClient(url, timeout_seconds, ssl_verify=verify_server,
                                   headers=headers, tls_options=options)

    def create_from_env(self) -> AgentRegistryClient:
        return self.create_client()

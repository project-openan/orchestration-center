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

from __future__ import annotations

from pathlib import Path

from common.util.config_util import get_conf
from host_agent import ControlPointContext, HostAgentConfig, HostAgentExecutor
from samples.spn_host_agent.control_point import SpnControlPoint
from samples.spn_host_agent.lifecycle import SpnExtensionLifecycle
from samples.spn_host_agent.registry import ConfiguredRegistryCardProvider


def create_spn_host_executor(all_agent_cards: list | None = None) -> HostAgentExecutor:
    """Compose the reusable HostAgent runtime with the SPN sample policy."""

    conf = get_conf()
    ssl_verify = str(conf.get("client_verify_server", "false")).lower() == "true"
    scheme = "https" if str(conf.get("enable_https", "true")).lower() == "true" else "http"
    orchestration_url = f"{scheme}://127.0.0.1:{conf.get('port', '5001')}"
    registry_url = conf.get("agent_registry_url") or "https://127.0.0.1:5000"
    credentials_path = Path(__file__).resolve().parents[1] / "agent_credentials.json"

    def create_control_point(context: ControlPointContext) -> SpnControlPoint:
        return SpnControlPoint(
            orch_url=context.orchestration_url,
            ssl_verify=context.ssl_verify,
            lang=context.lang,
        )

    return HostAgentExecutor(
        config=HostAgentConfig(
            orchestration_url=orchestration_url,
            registry_url=registry_url,
            ssl_verify=ssl_verify,
            # REQ74 P4 deployment admission: the sample Host must honor the
            # same server.conf keys as the center, or a configured pilot could
            # never pass this composition path.
            role_execution_mode=str(conf.get("role_execution_mode", "disabled")),
            deployment_environment=str(conf.get("deployment_environment", "production")),
        ),
        control_point_factory=create_control_point,
        extension_lifecycle=SpnExtensionLifecycle(
            all_agent_cards or [],
            str(credentials_path),
            ssl_verify,
        ),
        credentials_config=str(credentials_path),
        agent_card_provider=ConfiguredRegistryCardProvider(
            registry_url, {**conf, "ssl_verify": ssl_verify},
        ),
    )

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

import json
from pathlib import Path
from typing import List, Dict, Any

import yaml
from a2a.types import AgentCard
from google.protobuf.json_format import Parse
from loguru import logger


def _normalize_security_schemes(sec_schemes: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(sec_schemes, dict):
        return sec_schemes if sec_schemes else {}
    normalized = {}
    for name, scheme in sec_schemes.items():
        if not isinstance(scheme, dict):
            normalized[name] = scheme
            continue
        if any(k in scheme for k in (
            "httpAuthSecurityScheme", "apiKeySecurityScheme",
            "oauth2SecurityScheme", "openIdConnectSecurityScheme",
            "mtlsSecurityScheme",
        )):
            normalized[name] = scheme
            continue
        if "scheme" in scheme and isinstance(scheme["scheme"], str):
            http_auth = {"scheme": scheme["scheme"]}
            normalized[name] = {"httpAuthSecurityScheme": http_auth}
            continue
        normalized[name] = scheme
    return normalized


def _normalize_security_requirements(sec_reqs: List[Any]) -> List[Dict[str, Any]]:
    if not isinstance(sec_reqs, list):
        return []
    normalized = []
    for req in sec_reqs:
        if not isinstance(req, dict):
            continue
        schemes = req.get("schemes")
        if isinstance(schemes, list):
            normalized.append({"schemes": {s: {} for s in schemes}})
        elif isinstance(schemes, dict):
            normalized.append(req)
        else:
            normalized.append(req)
    return normalized


def _normalize_agent_dict(agent_dict: Dict[str, Any]) -> Dict[str, Any]:
    agent_dict = dict(agent_dict)
    sec_schemes = agent_dict.get("securitySchemes")
    if sec_schemes is not None:
        agent_dict["securitySchemes"] = _normalize_security_schemes(sec_schemes)
    sec_reqs = agent_dict.get("securityRequirements")
    if sec_reqs is not None:
        agent_dict["securityRequirements"] = _normalize_security_requirements(sec_reqs)
    if agent_dict.get("securitySchemes") and not agent_dict.get("securityRequirements"):
        scheme_names = list(agent_dict["securitySchemes"].keys())
        agent_dict["securityRequirements"] = [{"schemes": {s: {} for s in scheme_names}}]
        logger.debug(f"Auto-populated securityRequirements from securitySchemes: {scheme_names}")
    return agent_dict


class AgentCardLoader:
    """
    Load AgentCards from all YAML/JSON files in a directory.

    Usage:
        loader = AgentCardLoader(Path("samples/agentcard"))
        cards = loader.get_all_agent_cards()
    """

    def __init__(self, cards_dir: Path):
        self._cards_dir = Path(cards_dir)
        if not self._cards_dir.is_dir():
            raise ValueError(f"Agent cards directory not found: {self._cards_dir}")

    def _iter_card_files(self):
        for ext in ("*.yaml", "*.yml", "*.json"):
            yield from sorted(self._cards_dir.glob(ext))

    def _load_card_file(self, file_path: Path) -> List[Dict[str, Any]]:
        suffix = file_path.suffix.lower()
        with open(file_path, "r", encoding="utf-8") as f:
            if suffix in (".yaml", ".yml"):
                config = yaml.safe_load(f)
            else:
                config = json.load(f)

        if not config:
            logger.warning(f"Empty config file: {file_path}")
            return []
        if isinstance(config, list):
            return config
        if "agents" in config:
            agents = config["agents"]
            if not isinstance(agents, list):
                raise ValueError(f"'agents' field must be a list in: {file_path}")
            return agents
        logger.warning(f"No 'agents' key or array found in: {file_path}")
        return []

    def get_all_agent_cards(self) -> List[AgentCard]:
        cards = []
        for agent_dict in self.get_raw_agent_dicts():
            try:
                normalized = _normalize_agent_dict(agent_dict)
                agent_card = Parse(json.dumps(normalized), AgentCard())
                cards.append(agent_card)
            except Exception as e:
                logger.warning(f"Failed to parse AgentCard: {agent_dict.get('name', 'unknown')} - {e}")
        return cards

    def get_raw_agent_dicts(self) -> List[Dict[str, Any]]:
        agents = []
        for file_path in self._iter_card_files():
            try:
                agents.extend(self._load_card_file(file_path))
            except Exception as e:
                logger.warning(f"Failed to load agent cards from {file_path}: {e}")
        if not agents:
            raise ValueError(f"No agent card definitions found in: {self._cards_dir}")
        return agents

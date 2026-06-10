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
                agent_card = Parse(json.dumps(agent_dict), AgentCard())
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

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

import yaml
from pathlib import Path
from typing import List, Dict, Any
from a2a.types import AgentCard
from google.protobuf.json_format import Parse


class AgentCardLoader:
    """
    AgentCard library supporting initialization from config file or URL.
    """

    def __init__(self):
        """
        Initialize AgentCard library.
        """
        self.config_file = Path(__file__).parent / "agentcard" / "agent_cards.yaml"
        self._load_from_config_file(self.config_file)

    def _load_from_config_file(self, config_file: Path) -> None:
        """
        Load AgentCards from configuration file.

        Args:
            config_file: Configuration file path
        """
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if not config:
            raise ValueError(f"Configuration file is empty or has invalid format: {config_file}")
        # Load from agents field in configuration file
        self._load_from_config_data(config, str(config_file))

    def _load_from_config_data(self, config: Dict[str, Any], config_path: str) -> None:
        """
        Load AgentCards from configuration data.

        Args:
            config: Configuration data dictionary
            config_path: Configuration file path (for error messages)
        """
        if "agents" not in config:
            raise ValueError(f"Invalid configuration format, missing 'agents' field: {config_path}")

        agents_data = config["agents"]
        if not isinstance(agents_data, list):
            raise ValueError(f"The 'agents' field in configuration must be a list: {config_path}")

        self._agent_cards = []
        for agent_dict in agents_data:
            try:
                agent_card = Parse(json.dumps(agent_dict), AgentCard())
                self._agent_cards.append(agent_card)
            except Exception as e:
                raise ValueError(f"Failed to parse AgentCard: {agent_dict.get('name', 'unknown')} - {e}")

    def get_all_agent_cards(self) -> List[AgentCard]:
        """
        Get all AgentCards.

        Returns:
            List[AgentCard]: AgentCard list
        """
        return self._agent_cards.copy()

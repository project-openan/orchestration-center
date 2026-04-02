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

import yaml
import httpx
from pathlib import Path
from typing import List, Optional, Dict, Any
from a2a.types import AgentCard


class AgentCardLib:
    """
    AgentCard库，支持从配置文件或URL初始化并获取AgentCard列表。
    
    配置文件逻辑：
    1. 如果配置文件中包含 source_url 字段，则优先从该URL获取AgentCard
    2. 否则，使用配置文件中的 agents 字段
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化AgentCard库。
        
        Args:
            config_path: 配置文件路径，默认为 config/agent_cards.yaml
        """
        self._agent_cards: List[AgentCard] = []
        
        if config_path:
            config_file = Path(config_path)
        else:
            # 使用默认配置文件
            config_file = Path(__file__).parent.parent / "config" / "agent_cards.yaml"
        
        self._load_from_config_file(config_file)
    
    def _load_from_config_file(self, config_file: Path) -> None:
        """
        从配置文件加载AgentCard。
        
        Args:
            config_file: 配置文件路径
        """
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config:
            raise ValueError(f"配置文件为空或格式不正确: {config_file}")
        
        # 检查是否配置了source_url
        source_url = config.get("source_url")
        if source_url:
            # 从URL获取AgentCard
            self._load_from_url(source_url)
        else:
            # 从配置文件的agents字段加载
            self._load_from_config_data(config, str(config_file))
    
    def _load_from_config_data(self, config: Dict[str, Any], config_path: str) -> None:
        """
        从配置数据中加载AgentCard。
        
        Args:
            config: 配置数据字典
            config_path: 配置文件路径（用于错误信息）
        """
        if "agents" not in config:
            raise ValueError(f"配置文件格式不正确，缺少'agents'字段: {config_path}")
        
        agents_data = config["agents"]
        if not isinstance(agents_data, list):
            raise ValueError(f"配置文件中的'agents'字段必须是列表: {config_path}")
        
        self._agent_cards = []
        for agent_dict in agents_data:
            try:
                agent_card = AgentCard.model_validate(agent_dict)
                self._agent_cards.append(agent_card)
            except Exception as e:
                raise ValueError(f"解析AgentCard失败: {agent_dict.get('name', 'unknown')} - {e}")
    
    def _load_from_url(self, url: str) -> None:
        """
        从URL获取AgentCard。
        
        Args:
            url: 获取AgentCard的URL地址
        """
        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                self._agent_cards = [AgentCard.model_validate(item) for item in data]
            elif "agents" in data:
                self._agent_cards = [AgentCard.model_validate(item) for item in data["agents"]]
            else:
                raise ValueError(f"无法解析URL返回的数据格式: {data}")
        except Exception as e:
            raise RuntimeError(f"从URL获取AgentCard失败: {e}")

    def get_all_agent_cards(self) -> List[AgentCard]:
        """
        获取所有AgentCard。
        
        Returns:
            List[AgentCard]: AgentCard列表
        """
        return self._agent_cards.copy()

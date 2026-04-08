import yaml
import httpx
from pathlib import Path
from typing import List, Optional, Dict, Any
from a2a.types import AgentCard


class AgentCardLib:
    """
    AgentCard library, supporting initialization from configuration file or URL and retrieval of AgentCard list.
    
    Configuration file logic:
    1. If configuration file contains source_url field, prioritize fetching AgentCard from that URL
    2. Otherwise, use the agents field in configuration file
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize AgentCard library.
        
        Args:
            config_path: Configuration file path, defaults to config/agent_cards.yaml
        """
        self._agent_cards: List[AgentCard] = []
        
        if config_path:
            config_file = Path(config_path)
        else:
            # Use default configuration file
            config_file = Path(__file__).parent.parent / "config" / "agent_cards.yaml"
        
        self._load_from_config_file(config_file)
    
    def _load_from_config_file(self, config_file: Path) -> None:
        """
        Load AgentCard from configuration file.
        
        Args:
            config_file: Configuration file path
        """
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file does not exist: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config:
            raise ValueError(f"Configuration file is empty or malformed: {config_file}")
        
        # Check if source_url is configured
        source_url = config.get("source_url")
        if source_url:
            # Fetch AgentCard from URL
            self._load_from_url(source_url)
        else:
            # Load from agents field in configuration file
            self._load_from_config_data(config, str(config_file))
    
    def _load_from_config_data(self, config: Dict[str, Any], config_path: str) -> None:
        """
        Load AgentCard from configuration data.
        
        Args:
            config: Configuration data dictionary
            config_path: Configuration file path (for error messages)
        """
        if "agents" not in config:
            raise ValueError(f"Configuration file format incorrect, missing 'agents' field: {config_path}")
        
        agents_data = config["agents"]
        if not isinstance(agents_data, list):
            raise ValueError(f"The 'agents' field in configuration file must be a list: {config_path}")
        
        self._agent_cards = []
        for agent_dict in agents_data:
            try:
                agent_card = AgentCard.model_validate(agent_dict)
                self._agent_cards.append(agent_card)
            except Exception as e:
                raise ValueError(f"Failed to parse AgentCard: {agent_dict.get('name', 'unknown')} - {e}")
    
    def _load_from_url(self, url: str) -> None:
        """
        Fetch AgentCard from URL.
        
        Args:
            url: URL address to fetch AgentCard from
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
                raise ValueError(f"Cannot parse data format returned from URL: {data}")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch AgentCard from URL: {e}")

    def get_all_agent_cards(self) -> List[AgentCard]:
        """
        Get all AgentCards.
        
        Returns:
            List[AgentCard]: List of AgentCards
        """
        return self._agent_cards.copy()

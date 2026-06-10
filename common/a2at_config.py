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
import re
from pathlib import Path
from typing import Optional

from loguru import logger

LANG_MAP = {"en": "en-US", "zh": "zh-CN"}


def _default_env_path() -> Path:
    base = Path(os.path.abspath(__file__)).parent.parent
    return base / ".env"


def get_a2at_env_path(env_path: Path = None) -> Path:
    if env_path is not None:
        return env_path
    return _default_env_path()


def update_a2at_language(language: str, env_path: Path = None) -> None:
    path = get_a2at_env_path(env_path)
    lang_code = LANG_MAP.get(language, language)
    content = path.read_text(encoding='utf-8')
    updated = re.sub(r'^(A2AT_LANGUAGE=).*$', rf'\1{lang_code}', content, flags=re.MULTILINE)
    path.write_text(updated, encoding='utf-8')
    logger.info(f"Updated A2AT_LANGUAGE to {lang_code} in {path}")


def generate_env_from_llm_config(
    env_output_path: Optional[Path] = None,
    capability: str = "chat",
) -> Path:
    from common.llm.config.llm_config import get_model_config

    if env_output_path is None:
        env_output_path = _default_env_path()

    model_cfg = get_model_config(capability)
    if model_cfg is None:
        raise ValueError(f"LLM capability '{capability}' not found in llm_config.json")

    model = model_cfg.model
    api_key = model_cfg.api_key
    base_url = model_cfg.url

    if not model:
        raise ValueError("Missing 'model' in LLM config")

    a2at_provider = "deepseek"
    if "deepseek" in base_url.lower():
        a2at_provider = "deepseek"

    env_content = f"""# Copyright (c) 2026 Huawei Technologies Co., Ltd.
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

# A2A-T SDK Configuration
# Auto-generated from common/config/llm_config.json (capability: {capability})

# Prompt runtime
A2AT_LANGUAGE=zh-CN
A2AT_PROMPT_SOURCE_TYPE=local_file
A2AT_PROMPT_RESOURCE_LOCAL_ROOT_DIR=

# Prompt compliance
A2AT_PROMPT_COMPLIANCE_ENABLED=false
A2AT_PROMPT_COMPLIANCE_GUARDRAIL_PROVIDER=noop

# LLM runtime
A2AT_LLM_PROVIDER={a2at_provider}
A2AT_LLM_MODEL={model}
A2AT_LLM_API_KEY={api_key}
A2AT_LLM_BASE_URL={base_url}
A2AT_LLM_MAX_TOKENS=2000
A2AT_LLM_TEMPERATURE=0
A2AT_LLM_TIMEOUT_SECONDS=60
A2AT_LLM_HISTORY_WINDOW=10
A2AT_LLM_SESSION_MAX_TOTAL=300
A2AT_LLM_SESSION_MAX_PER_PROVIDER=100

# Negotiation
A2AT_NEGOTIATION_STATE_STORE_TYPE=in_memory
"""

    env_output_path.write_text(env_content, encoding='utf-8')
    logger.info(f"Generated A2AT .env file at: {env_output_path}")
    return env_output_path


def ensure_env_file_exists() -> Path:
    env_path = _default_env_path()
    if not env_path.exists():
        logger.warning("A2AT .env file not found, generating from LLM config")
        return generate_env_from_llm_config()

    env_content = env_path.read_text(encoding='utf-8')
    if "A2AT_LLM_MODEL=" in env_content:
        lines = env_content.split('\n')
        model_lines = [l for l in lines if l.startswith("A2AT_LLM_MODEL=")]
        if model_lines and model_lines[0].strip() == "A2AT_LLM_MODEL=":
            logger.info("A2AT .env file has empty LLM config, regenerating")
            return generate_env_from_llm_config()

    return env_path

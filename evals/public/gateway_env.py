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

"""Load the Blue-Zone unified gateway API key into the process environment.

The key lives in the DSH credentials file (~/.dsh/.credentials.yaml) as
``LANQU_GATEWAY_API_KEY`` (same injection path as AgentFrameWork's start
script). The value is never logged or returned to callers.
"""

import os
import re
from pathlib import Path

ENV_VAR = "LANQU_GATEWAY_API_KEY"


def load_gateway_key() -> bool:
    """Populate os.environ[ENV_VAR] from ~/.dsh/.credentials.yaml if absent.

    Returns True when the environment variable is available afterwards.
    """
    if os.environ.get(ENV_VAR):
        return True
    value = read_key_from_file(Path.home() / ".dsh" / ".credentials.yaml", ENV_VAR)
    if not value:
        return False
    os.environ[ENV_VAR] = value
    return True


def read_key_from_file(path: Path, variable: str) -> str:
    """Extract a variable value from a credentials/env file; never logs it."""
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(
        rf"^\s*#?\s*{re.escape(variable)}\s*[:=]\s*[\"']?([A-Za-z0-9._\-]+)", content,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def load_env_var_from_file(env_file, variable: str) -> bool:
    """Load one variable (e.g. DEEPSEEK_API_KEY) from an env file into os.environ.

    Existing process values win. Returns True when available afterwards.
    """
    if os.environ.get(variable):
        return True
    value = read_key_from_file(Path(env_file), variable)
    if not value:
        return False
    os.environ[variable] = value
    return True

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Guard deprecated/private model inputs at both build-upload boundaries."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", [".dockerignore", ".gcloudignore"])
def test_private_and_legacy_model_inputs_excluded(name):
    patterns = set((ROOT / name).read_text(encoding="utf-8").splitlines())
    assert {"common/config/llm_config.json", "etc/config/models.yaml",
            "etc/conf/server.conf", "**/auth.local.json"} <= patterns


@pytest.mark.parametrize("provider", ["aoc_signed", "unknown"])
def test_provider_failure_diagnostic_portable_bash(provider, tmp_path):
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    if not bash:
        pytest.skip("Bash unavailable")
    workspace = str(tmp_path)
    if os.name == "nt":
        workspace = subprocess.check_output(
            [bash, "-c", 'cygpath -u "$1"', "test", workspace], text=True).strip()
    env = {**os.environ, "APP_HOME": workspace, "LLM_CHAT_MODEL": "model",
           "LLM_CHAT_URL": "https://example.invalid/chat", "LLM_CHAT_PROVIDER": provider}
    env.pop("LLM_CONFIG_FILE", None)
    result = subprocess.run([bash, str(ROOT / "docker-entrypoint.sh"), "true"],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "provide a complete models.yaml" in result.stderr

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual nginx entrypoint hook without claiming nginx runtime QA."""
import os
from pathlib import Path
import shutil
import subprocess
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("BASH_BIN") or shutil.which("bash")


def test_frontend_hook_is_executable_in_image():
    # Nginx sources *.envsh only when the executable bit is present.
    dockerfile = (ROOT / "workflow-designer/Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"chmod 0?755 /docker-entrypoint.d/15-openan-backend.envsh", dockerfile)


def test_compose_cookie_scheme_matches_http_frontend_by_default():
    import yaml
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["orchestration-center"]["environment"]
    assert env["ORCH_PUBLIC_SCHEME"] == "${ORCH_PUBLIC_SCHEME:-http}"


def run_hook(tmp_path, env):
    if not BASH:
        pytest.skip("Set BASH_BIN to a working Bash executable")
    source = ROOT / "workflow-designer/15-openan-backend.envsh"
    clean = {k: v for k, v in os.environ.items()
             if not k.startswith(("BACKEND_", "ORCH_ENABLE_HTTPS"))}
    clean.update({"BACKEND_HOST": "orchestration-center", **env})
    return subprocess.run(
        [BASH, "-c", '. "$1"; printf "%s\\n%s\\n" "$BACKEND_SCHEME" "$BACKEND_TLS_OPTIONS"',
         "hook-test", str(source)],
        env=clean, capture_output=True, text=True, timeout=10)


def test_http_hook_does_not_require_pki(tmp_path):
    result = run_hook(tmp_path, {})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["http", ""]


def test_https_default_requires_trust(tmp_path):
    result = run_hook(tmp_path, {"ORCH_ENABLE_HTTPS": "true"})
    assert result.returncode != 0
    assert "requires BACKEND_CA_FILE" in result.stderr


def test_https_explicit_skip_and_incomplete_mtls(tmp_path):
    settings = {"BACKEND_SCHEME": "https", "BACKEND_VERIFY_SERVER": "false"}
    result = run_hook(tmp_path, settings)
    assert result.returncode == 0, result.stderr
    assert "proxy_ssl_verify off;" in result.stdout
    settings["BACKEND_CLIENT_CERT"] = "/missing-cert"
    result = run_hook(tmp_path, settings)
    assert result.returncode != 0
    assert "Both upstream mTLS files" in result.stderr


def test_https_ca_and_mtls_files_are_emitted(tmp_path):
    material = tmp_path / "pki"
    material.mkdir()
    for name in ("ca.pem", "client.pem", "client.key"):
        (material / name).write_text("synthetic fixture", encoding="utf-8")
    if not BASH:
        pytest.skip("Bash unavailable")
    if os.name == "nt":
        directory = subprocess.check_output(
            [BASH, "-c", 'cygpath -u "$1"', "path-test", str(material)],
            text=True).strip()
    else:
        directory = str(material)
    result = run_hook(tmp_path, {"BACKEND_SCHEME": "https",
                                "BACKEND_CA_FILE": directory + "/ca.pem",
                                "BACKEND_CLIENT_CERT": directory + "/client.pem",
                                "BACKEND_CLIENT_KEY": directory + "/client.key"})
    assert result.returncode == 0, result.stderr
    assert "proxy_ssl_verify on;" in result.stdout
    assert "proxy_ssl_certificate_key" in result.stdout

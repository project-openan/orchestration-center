# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0
"""Full start.main in a fresh child process; real HTTP/HTTPS file-mode APIs."""
import hashlib
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "test-only-process-machine-token-000000000000000"


@pytest.mark.parametrize("protocol", ["http", "https"])
@pytest.mark.parametrize("public_scheme", ["", "http", "https"])
def test_fresh_service_login_cookie_and_workflow_crud(protocol, public_scheme, tmp_path, sample_psop_dict):
    workspace = tmp_path / "service"
    for package in ("orchestrate", "host_agent", "database", "common"):
        for path in (ROOT / package).rglob("*.py"):
            target = workspace / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    conf_dir = workspace / "etc/conf"
    conf_dir.mkdir(parents=True)
    shutil.copyfile(ROOT / "etc/conf/server.conf.example", conf_dir / "server.conf")
    for name in ("server.properties", "log_config.conf"):
        shutil.copyfile(ROOT / "etc/conf" / name, conf_dir / name)
    if protocol == "https":
        from common.cert.certificate_generator import CertificateGenerator
        import generate_selfsign_cert as cli
        ssl_dir = workspace / "etc/ssl"
        ssl_dir.mkdir(parents=True)
        assert CertificateGenerator().generate_self_signed_cert(str(ssl_dir), "serverAuth", "Process#2026")
        cli._write_deploy_files(str(ssl_dir), "Process#2026", plain_key=False)
        verify = ssl.create_default_context(cafile=str(ssl_dir / "trust.cer"))
    else:
        verify = True
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ORCH_", "OC_", "DB_", "MYSQL_", "PERSISTENCE_", "REGISTRY_", "LLM_"))}
    env.pop("TESTING", None)
    env.pop("PORT", None)
    env.update(PYTHONPATH=str(workspace), PYTHON_DOTENV_DISABLED="1",
               ORCH_IP="127.0.0.1", ORCH_PORT=str(port), PERSISTENCE_MODE="file",
               ORCH_ENABLE_HTTPS=str(protocol == "https").lower(), ORCH_VERIFY_CLIENT="false",
               ORCH_PUBLIC_SCHEME=public_scheme,
               ORCH_API_TOKEN=TOKEN, ORCH_ACCESS_PASSWORD=hashlib.sha256(b"ProcessUser9!").hexdigest())
    with (tmp_path / "service.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "orchestrate.start"], cwd=workspace,
                                   env=env, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=f"{protocol}://127.0.0.1:{port}", verify=verify, trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        pytest.fail((tmp_path / "service.log").read_text(encoding="utf-8")[-4000:])
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        pytest.fail("Isolated service readiness timeout; see service.log")
                    time.sleep(0.1)
                base = "/rest/v1/orchestrate"
                assert client.get(base + "/workflows").status_code == 401
                login = client.post(base + "/auth/login", json={"username": "admin", "password": "ProcessUser9!"})
                assert login.status_code == 200, login.text
                assert ("; secure" in login.headers["set-cookie"].lower()) == ((public_scheme or protocol) == "https")
                if protocol == "http" and public_scheme == "https":
                    # The client here connects directly, not through the public
                    # HTTPS gateway. Real browsers send the cookie to that gateway;
                    # preserve that header while exercising the plain backend.
                    client.headers["Cookie"] = login.headers["set-cookie"].split(";", 1)[0]
                response = client.post(base + "/workflows", json={"psop": sample_psop_dict})
                assert response.status_code == 201, response.text
                workflow_id = response.json()["data"]["workflow_id"]
                target = base + "/workflows/" + workflow_id
                assert client.get(target).status_code == 200
                external = "/api/v1/orchestrate/psop/" + workflow_id
                assert client.get(external).status_code == 401  # UI cookie is not a machine credential.
                assert client.get(external, headers={"Authorization": "Bearer " + TOKEN}).status_code == 200
                assert client.delete(target).status_code == 200
                assert client.get(target).status_code == 404
                assert client.post(base + "/auth/logout").status_code == 200
                client.headers.pop("Cookie", None)
                assert client.get(base + "/workflows").status_code == 401
        finally:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Real HTTP/TLS transport; injected SQL failures, not a real DB acceptance run."""

import ipaddress
import socket
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
import uvicorn


def _tls_files(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]), critical=False).sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "server.pem", tmp_path / "server-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    return cert_path, key_path


@pytest.mark.parametrize("mode", ["mysql", "postgresql"])
@pytest.mark.parametrize("transport", ["http", "https"])
def test_storage_failure_over_actual_listener(mode, transport, tmp_path, monkeypatch, sample_psop_dict):
    from common.util import persistence_mode
    from database.utils import user_store
    from orchestrate.core.shared_handlers import SharedHandlers
    from orchestrate.handlers import psop_processor, execution_record_processor
    from orchestrate.persistence import context, create_backend, StorageContext
    from orchestrate.server import frontend_support_server as server, auth, middleware
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": mode})
    monkeypatch.setattr(context, "_persistence_context", StorageContext(create_backend(mode)))
    for attr in ("_save_handle", "_delete_handle", "_retrieval"):
        monkeypatch.setattr(SharedHandlers, attr, None)
    monkeypatch.setattr(auth, "is_auth_enabled", lambda: False)
    monkeypatch.setattr(server, "is_auth_enabled", lambda: True)
    monkeypatch.setattr(middleware, "limiter", MovingWindowRateLimiter(MemoryStorage()))
    for module in (psop_processor, execution_record_processor, user_store):
        monkeypatch.setattr(module, "create_connection", lambda: None)

    from orchestrate.server import external_auth
    monkeypatch.setenv("ORCH_API_TOKEN", "transport-regression-token-000000000000")
    monkeypatch.setattr(auth, "get_conf", lambda: {"external.auth.mode": "bearer"})

    options = {}
    verify = True
    if transport == "https":
        cert_path, key_path = _tls_files(tmp_path)
        options.update(ssl_certfile=str(cert_path), ssl_keyfile=str(key_path))
        verify = ssl.create_default_context(cafile=str(cert_path))

    # Pre-bind an ephemeral loopback port; no collision and no production listener.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.listen(32)
    config = uvicorn.Config(server.app, log_level="error", lifespan="off", **options)
    runner = uvicorn.Server(config)
    thread = threading.Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not runner.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started, "HTTP listener failed to start"
        with httpx.Client(base_url=f"{transport}://127.0.0.1:{port}", verify=verify,
                          trust_env=False, timeout=5,
                          headers={"Authorization": "Bearer transport-regression-token-000000000000"}) as client:
            for path in (
                "/rest/v1/orchestrate/workflows", "/rest/v1/orchestrate/workflows/absent",
                "/rest/v1/orchestrate/execution-records", "/api/v1/orchestrate/psop/absent",
                "/api/v1/executions", "/api/v1/executions/absent",
            ):
                response = client.get(path)
                assert response.status_code == 503, (path, response.text)
            response = client.post("/rest/v1/orchestrate/workflows", json={"psop": sample_psop_dict})
            assert response.status_code == 503, response.text
            response = client.delete("/rest/v1/orchestrate/execution-records/absent")
            assert response.status_code == 503, response.text
            response = client.post("/rest/v1/orchestrate/auth/login", json={
                "username": "admin", "password": "not-a-real-password",
            })
            assert response.status_code == 503, response.text

            # A successful empty query must still mean missing data, not outage.
            monkeypatch.setattr(psop_processor, "create_connection", MagicMock())
            monkeypatch.setattr(psop_processor, "execute_query", lambda *args: ([], None))
            assert client.get("/rest/v1/orchestrate/workflows/absent").status_code == 404
            monkeypatch.setattr(psop_processor, "execute_query", lambda *args: ([('{bad-json',)], None))
            response = client.get("/api/v1/orchestrate/psop/absent")
            assert response.status_code == 500
            assert "bad-json" not in response.text
    finally:
        runner.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "HTTP listener was not cleaned up"

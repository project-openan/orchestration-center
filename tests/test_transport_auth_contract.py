# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Authentication across real HTTP/TLS sockets, not merely ASGI test clients."""
import socket
import ssl
import threading
import time
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn
from fastapi import HTTPException, Request

from orchestrate.server import auth, external_auth, frontend_support_server as server
from test_storage_http_transport import _tls_files

TOKEN = "test-only-machine-token-000000000000000"


@pytest.mark.parametrize("protocol", ["http", "https"])
def test_machine_token_is_independent_of_user_cookie_and_transport(protocol, tmp_path, monkeypatch):
    monkeypatch.setenv("ORCH_API_TOKEN", TOKEN)
    monkeypatch.setattr(auth, "get_conf", lambda: {
        "enable_https": protocol == "https", "verify_client": "false",
        "external.auth.mode": "auto",
    })
    options, verify = {}, True
    if protocol == "https":
        cert, key = _tls_files(tmp_path)
        options = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        verify = ssl.create_default_context(cafile=str(cert))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    runner = uvicorn.Server(uvicorn.Config(server.app, lifespan="off", log_level="error", **options))
    thread = threading.Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not runner.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started
        with httpx.Client(base_url=f"{protocol}://127.0.0.1:{listener.getsockname()[1]}",
                          verify=verify, trust_env=False) as client:
            path = "/api/v1/does-not-exist"
            denied = client.get(path)
            assert denied.status_code == 401
            assert denied.headers["www-authenticate"] == "Bearer"
            assert client.get(path, params={"access_token": TOKEN}).status_code == 401
            client.cookies.set("session_token", TOKEN)
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"Authorization": "Bearer incorrect"}).status_code == 401
            assert client.get(path, headers=[
                ("Authorization", "Bearer " + TOKEN), ("Authorization", "Bearer " + TOKEN),
            ]).status_code == 401
            # Authentication succeeded: the router, not authentication, returns 404.
            assert client.get(path, headers={"Authorization": "bearer " + TOKEN}).status_code == 404
            assert client.get("/health").status_code == 200
    finally:
        runner.should_exit = True
        thread.join(10)
        listener.close()
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_mtls_identity_cannot_be_forged_with_forwarded_headers():
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [
        (b"x-ssl-client-dn", b"CN=admin"), (b"x-forwarded-proto", b"https"),
    ]})
    conf = {"external.auth.mode": "mtls", "enable_https": "true", "verify_client": "true"}
    with pytest.raises(HTTPException) as exc:
        await external_auth.authenticate_external(request, conf)
    assert exc.value.status_code == 401
    request.scope["tls_peer_cert"] = {"subject": ((("commonName", "test-client"),),)}
    assert (await external_auth.authenticate_external(request, conf)).subject == "mtls-client"


@pytest.mark.asyncio
async def test_custom_provider_contract_fails_closed(monkeypatch):
    from common.custom import HandlerRegistry, InterfaceType
    class Provider:
        handle = AsyncMock(return_value=None)
        aclose = AsyncMock()
    monkeypatch.setitem(HandlerRegistry._overrides, InterfaceType.AUTHENTICATE_EXTERNAL.value, Provider)
    external_auth._custom_handler.cache_clear()
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    try:
        with pytest.raises(HTTPException) as exc:
            await external_auth.authenticate_external(request, {"external.auth.mode": "custom"})
        assert exc.value.status_code == 503
        Provider.handle.return_value = external_auth.MachineIdentity("business-client")
        assert (await external_auth.authenticate_external(request, {"external.auth.mode": "custom"})).subject == "business-client"
    finally:
        await external_auth.close_external_auth()
    Provider.aclose.assert_awaited_once()


def test_file_mode_does_not_accept_database_bootstrap_password(monkeypatch):
    from orchestrate.server.security_preflight import security_preflight, SecurityPreflightError
    monkeypatch.setenv("OC_ADMIN_INITIAL_PASSWORD", "database-only-initial-password")
    monkeypatch.setenv("ORCH_API_TOKEN", TOKEN)
    with pytest.raises(SecurityPreflightError):
        security_preflight({"ip": "0.0.0.0", "enable_https": "false", "persistence_mode": "file"})


def test_readonly_tls_mount_permissions(monkeypatch):
    import errno
    from common.util import conf_util
    from types import SimpleNamespace
    monkeypatch.setattr(conf_util.os, "chmod", lambda *args: (_ for _ in ()).throw(OSError(errno.EROFS, "read-only")))
    monkeypatch.setattr(conf_util.os, "stat", lambda path: SimpleNamespace(st_mode=0o440))
    conf_util._restrict_ssl_permissions("deployment-secret", 0o600)
    monkeypatch.setattr(conf_util.os, "stat", lambda path: SimpleNamespace(st_mode=0o444))
    with pytest.raises(PermissionError):
        conf_util._restrict_ssl_permissions("world-readable-secret", 0o600)

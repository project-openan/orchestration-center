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

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI, Request
from loguru import logger

from host_agent.auth import HostAuthenticationProvider


@dataclass(frozen=True)
class HostTlsConfig:
    """Explicit HTTPS material; an empty password path means an unencrypted key."""

    cert_file: str
    key_file: str
    password_file: str = ""


def create_agent_app(
    agent_card: AgentCard,
    agent_executor,
    *,
    auth_provider: HostAuthenticationProvider | None = None,
) -> FastAPI:
    """Assemble A2A routes for one AgentCard-backed executor."""
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    app = FastAPI()

    if (
        auth_provider is not None
        and agent_card.security_schemes
        and agent_card.security_requirements
    ):
        @app.api_route(auth_provider.login_path, methods=["PUT", "POST"])
        async def _agent_login(request: Request):
            return await auth_provider.authenticate(request)

    app.routes.extend(create_agent_card_routes(agent_card=agent_card))

    for interface in agent_card.supported_interfaces:
        if not interface.url:
            continue
        path = urlparse(interface.url).path.rstrip("/") or ""
        if interface.protocol_binding == "JSONRPC":
            app.routes.extend(create_jsonrpc_routes(
                request_handler=request_handler,
                rpc_url=path,
            ))
        elif interface.protocol_binding == "HTTP+JSON":
            app.routes.extend(create_rest_routes(
                request_handler=request_handler,
                path_prefix=path,
            ))
    return app


async def start_agent_server(
    agent_card: AgentCard,
    agent_executor,
    port: int,
    host: str = "127.0.0.1",
    auth_provider: HostAuthenticationProvider | None = None,
    tls_config: HostTlsConfig | None = None,
) -> None:
    """Start one Host Agent server and manage its lifecycle."""
    agent_name = agent_card.name
    agent_url = ""
    if agent_card.supported_interfaces:
        agent_url = agent_card.supported_interfaces[0].url or ""

    ssl_kwargs: dict[str, str] = {}
    schemes = {urlparse(interface.url).scheme for interface in agent_card.supported_interfaces
               if interface.url and interface.protocol_binding in {"JSONRPC", "HTTP+JSON"}}
    if schemes - {"http", "https"} or len(schemes) > 1:
        raise ValueError("Host Agent HTTP interfaces must declare a single HTTP or HTTPS protocol")
    if schemes == {"https"} or (not schemes and agent_url.startswith("https://")):
        # parents[1] = the repository (or install) root that contains etc/ssl.
        # host_agent/service.py sits one level below it; parents[2] would point
        # outside the project and silently degrade https agent servers to HTTP.
        ssl_dir = Path(__file__).resolve().parents[1] / "etc" / "ssl"
        cert_path = ssl_dir / "server.cer"
        if not cert_path.is_file():
            cert_path = ssl_dir / "server1.cer"
        key_path = ssl_dir / "server_key.pem"
        nopass_key_path = ssl_dir / "server_key_nopass.pem"
        password_path = ssl_dir / "cert_pwd"
        if tls_config is not None:
            cert_path = Path(tls_config.cert_file)
            key_path = Path(tls_config.key_file)
            nopass_key_path = key_path
            password_path = Path(tls_config.password_file) if tls_config.password_file else None
        if tls_config is not None and password_path is not None and not password_path.is_file():
            raise ValueError("Host Agent TLS password file is missing")
        if cert_path.is_file() and key_path.is_file():
            actual_key = nopass_key_path if nopass_key_path.is_file() else key_path
            ssl_kwargs["ssl_certfile"] = str(cert_path)
            ssl_kwargs["ssl_keyfile"] = str(actual_key)
            if tls_config is not None or not nopass_key_path.is_file():
                if password_path is not None and password_path.is_file():
                    ssl_kwargs["ssl_keyfile_password"] = password_path.read_text(
                        encoding="utf-8"
                    ).strip()
            logger.info(f"Agent {agent_name!r} starting with HTTPS")
        else:
            raise ValueError(f"Agent {agent_name!r} declares HTTPS but TLS certificate/key is missing")

    app = create_agent_app(
        agent_card,
        agent_executor,
        auth_provider=auth_provider,
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=2,
        **ssl_kwargs,
    )
    server = uvicorn.Server(config)
    try:
        start_hook = getattr(agent_executor, "start", None)
        if start_hook is not None:
            result = start_hook()
            if asyncio.iscoroutine(result):
                await result
        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        close_hook = getattr(agent_executor, "aclose", None)
        if close_hook is not None:
            result = close_hook()
            if asyncio.iscoroutine(result):
                await result

from __future__ import annotations

import asyncio
import secrets
import time
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
from starlette.responses import JSONResponse


def create_agent_app(
    agent_card: AgentCard,
    agent_executor,
) -> FastAPI:
    """Assemble A2A routes for one AgentCard-backed executor."""
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    app = FastAPI()

    if agent_card.security_schemes and agent_card.security_requirements:
        login_path = "/rest/plat/smapp/v1/oauth/token"
        valid_tokens: dict[str, float] = {}

        @app.api_route(login_path, methods=["PUT", "POST"])
        async def _agent_login(request: Request):
            content_type = request.headers.get("content-type", "")
            if "json" in content_type:
                body = await request.json()
            elif "form" in content_type:
                form = await request.form()
                body = dict(form)
            else:
                body = {}
            username = body.get("userName") or body.get("username")
            password = body.get("value") or body.get("password")
            if username == "admin" and password == "Admin@123":
                token = secrets.token_urlsafe(24)
                valid_tokens[token] = time.time() + 3600
                return {"accessSession": token}
            return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

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
) -> None:
    """Start one Host Agent server and manage its lifecycle."""
    app = create_agent_app(agent_card, agent_executor)
    agent_name = agent_card.name
    agent_url = ""
    if agent_card.supported_interfaces:
        agent_url = agent_card.supported_interfaces[0].url or ""

    ssl_kwargs: dict[str, str] = {}
    if agent_url.startswith("https://"):
        ssl_dir = Path(__file__).resolve().parents[2] / "etc" / "ssl"
        cert_path = ssl_dir / "server.cer"
        if not cert_path.is_file():
            cert_path = ssl_dir / "server1.cer"
        key_path = ssl_dir / "server_key.pem"
        nopass_key_path = ssl_dir / "server_key_nopass.pem"
        if cert_path.is_file() and key_path.is_file():
            actual_key = nopass_key_path if nopass_key_path.is_file() else key_path
            ssl_kwargs["ssl_certfile"] = str(cert_path)
            ssl_kwargs["ssl_keyfile"] = str(actual_key)
            if not nopass_key_path.is_file():
                password_path = ssl_dir / "cert_pwd"
                if password_path.is_file():
                    ssl_kwargs["ssl_keyfile_password"] = password_path.read_text(
                        encoding="utf-8"
                    ).strip()
            logger.info(f"Agent {agent_name!r} starting with HTTPS")
        else:
            logger.warning(
                f"Agent {agent_name!r} URL is https but SSL certificates are missing"
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
    except (SystemExit, asyncio.CancelledError):
        pass
    finally:
        close_hook = getattr(agent_executor, "aclose", None)
        if close_hook is not None:
            result = close_hook()
            if asyncio.iscoroutine(result):
                await result

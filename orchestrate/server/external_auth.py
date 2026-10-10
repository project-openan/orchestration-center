# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Machine API authentication, independent of browser sessions and transport."""

import hmac
import importlib
import os
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, Request

from common.custom import HandlerRegistry, InterfaceType


@dataclass(frozen=True)
class MachineIdentity:
    subject: str


def external_auth_mode(conf: dict) -> str:
    mode = str(conf.get("external.auth.mode", "auto")).strip().lower()
    if mode == "auto":
        mtls = (str(conf.get("enable_https", "true")).lower() == "true"
                and str(conf.get("verify_client", "true")).lower() == "true")
        return "mtls" if mtls else "bearer"
    if mode not in {"mtls", "bearer", "custom"}:
        raise ValueError("external.auth.mode must be auto, mtls, bearer or custom")
    return mode


def api_token(conf: dict) -> str:
    name = str(conf.get("external.auth.token_env", "ORCH_API_TOKEN")).strip()
    return os.environ.get(name, "") if name else ""


def external_auth_configured(conf: dict) -> bool:
    mode = external_auth_mode(conf)
    if mode == "mtls":
        return (str(conf.get("enable_https", "true")).lower() == "true"
                and str(conf.get("verify_client", "true")).lower() == "true")
    if mode == "custom":
        return HandlerRegistry.get_extension_override(InterfaceType.AUTHENTICATE_EXTERNAL) is not None
    return len(api_token(conf).encode("utf-8")) >= 32


@lru_cache(maxsize=1)
def _custom_handler():
    cls = HandlerRegistry.get_extension_override(InterfaceType.AUTHENTICATE_EXTERNAL)
    if cls is None:
        raise HTTPException(503, "External authentication provider unavailable")
    return cls()


async def close_external_auth():
    if _custom_handler.cache_info().currsize:
        handler = _custom_handler()
        _custom_handler.cache_clear()
        if hasattr(handler, "aclose"):
            await handler.aclose()


async def authenticate_external(request: Request, conf: dict) -> MachineIdentity:
    mode = external_auth_mode(conf)
    if mode == "custom":
        try:
            identity = await _custom_handler().handle(request)
            if not isinstance(identity, MachineIdentity) or not identity.subject:
                raise ValueError("Invalid authentication provider result")
            return identity
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "External authentication provider unavailable") from None
    if mode == "mtls":
        if not external_auth_configured(conf):
            raise HTTPException(503, "mTLS authentication requires HTTPS and client verification")
        # Evidence comes from the actual transport, never a forwarded header.
        if request.scope.get("tls_peer_cert"):
            return MachineIdentity("mtls-client")
        raise HTTPException(401, "Verified client certificate required")
    expected = api_token(conf)
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(503, "External Bearer credential unavailable")
    values = request.headers.getlist("authorization")
    parts = values[0].split() if len(values) == 1 else []
    if (len(parts) == 2 and parts[0].lower() == "bearer"
            and hmac.compare_digest(parts[1].encode("utf-8"), expected.encode("utf-8"))):
        return MachineIdentity("configured-api-client")
    raise HTTPException(401, "Valid Bearer token required", headers={"WWW-Authenticate": "Bearer"})


def install_peer_certificate_injection():
    """Expose verified TLS transport evidence on h11 and httptools requests."""
    for module_name in ("uvicorn.protocols.http.h11_impl", "uvicorn.protocols.http.httptools_impl"):
        try:
            cycle = importlib.import_module(module_name).RequestResponseCycle
        except ImportError:
            continue
        original = cycle.run_asgi
        if getattr(original, "_orch_peer_cert", False):
            continue

        def wrap(callback):
            async def run(self, app):
                transport = getattr(self, "transport", None)
                ssl_object = transport.get_extra_info("ssl_object") if transport else None
                self.scope["tls_peer_cert"] = ssl_object.getpeercert() if ssl_object else None
                return await callback(self, app)
            run._orch_peer_cert = True
            return run
        cycle.run_asgi = wrap(original)


install_peer_certificate_injection()

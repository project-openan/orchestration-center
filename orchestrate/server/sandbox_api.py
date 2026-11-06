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

"""Sandbox verification routes shared by internal and external APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from common.util.config_util import get_conf
from orchestrate.core.model.psop import PSOP
from orchestrate.sandbox.control_point import SandboxControlPoint
from orchestrate.sandbox.models import StubScenario
from orchestrate.sandbox.service import SandboxService
from orchestrate.sandbox.store import SandboxStore
from orchestrate.sandbox.validation import ROLE_SANDBOX_NOT_SUPPORTED, require_instance_workflow
from orchestrate.server.middleware import RateLimiter
from orchestrate.server.response_utils import created, get_agent_cards, ok
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.server.durable_api import principal_for_request, _identity_snapshot
from orchestrate.persistence.errors import StorageError
from orchestrate.server.storage_error_response import storage_http_exception
import asyncio

config = get_conf()
sandbox_service = SandboxService(
    control_point_factory=SandboxControlPoint,
    store=SandboxStore(),
    max_concurrent_runs=int(config.get("sandbox_max_concurrent_runs", 4)),
    run_timeout_seconds=float(config.get("sandbox_run_timeout_seconds", 60)),
)
sandbox_router = APIRouter()


class SandboxRunRequest(BaseModel):
    scenario: StubScenario = Field(StubScenario.SUCCESS, description="Sandbox response scenario")
    runtime_intent: str | None = Field(None, max_length=10000)
    templates: list[dict] = Field(default_factory=list, max_length=200)
    psop: dict | None = Field(None, description="Current editor snapshot; allows unsaved workflow verification")
    lang: Literal["zh", "en"] = Field("zh", description="Report language")


@sandbox_router.post("/sandbox/{workflow_id}/run", status_code=202)
async def start_sandbox_run(
    workflow_id: str,
    body: SandboxRunRequest,
    request: Request,
    _: Any = Depends(RateLimiter(config, "ext_execute_by_id")),
):
    """Start an isolated Stub-based workflow verification."""
    try:
        if body.psop is not None:
            try:
                psop = PSOP.model_validate(body.psop)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid workflow snapshot: {exc}") from exc
        else:
            psop = SharedHandlers.retrieval().get_psop_by_id(workflow_id)
            if not psop:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        try:
            require_instance_workflow(psop)
        except ValueError as exc:
            logger.warning("[Sandbox] rejected workflow_id={} code={}", psop.id, ROLE_SANDBOX_NOT_SUPPORTED)
            raise HTTPException(status_code=422, detail={
                "code": ROLE_SANDBOX_NOT_SUPPORTED,
                "message": "Role workflows are not supported by the instance sandbox",
            }) from exc
        try:
            templates = sandbox_service.validate_templates(body.templates)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        agent_cards = await get_agent_cards()
        verification_id = await sandbox_service.start(
            psop,
            agent_cards,
            scenario=body.scenario,
            runtime_intent=body.runtime_intent or psop.name or workflow_id,
            templates=templates,
            lang=body.lang,
            principal=principal_for_request(request),
            identity=_identity_snapshot(request),
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return created(
            data={"verification_id": verification_id, "status": "queued"},
            message="Sandbox verification started",
        )
    except HTTPException:
        raise
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to start sandbox: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start sandbox verification") from exc


@sandbox_router.get("/sandbox/verifications")
async def list_sandbox_reports(
    request: Request,
    _: Any = Depends(RateLimiter(config, "list_executions")),
):
    try:
        return ok(data=await asyncio.to_thread(sandbox_service.list_reports, principal_for_request(request)))
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to list sandbox reports: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list sandbox reports") from exc


@sandbox_router.get("/sandbox/verifications/{verification_id}")
async def get_sandbox_report(
    verification_id: str,
    request: Request,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        payload = await asyncio.to_thread(sandbox_service.report, verification_id, principal_for_request(request))
        if payload is None:
            status = await asyncio.to_thread(sandbox_service.status, verification_id, principal_for_request(request))
            if status is None:
                raise HTTPException(status_code=404, detail="Sandbox verification not found")
            return ok(data=status)
        return ok(data=payload)
    except HTTPException:
        raise
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to get sandbox report: {exc}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox report") from exc


@sandbox_router.delete("/sandbox/verifications/{verification_id}")
async def delete_sandbox_report(
    verification_id: str,
    request: Request,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        deleted = await sandbox_service.cancel_and_delete(verification_id, principal_for_request(request))
        if not deleted:
            raise HTTPException(status_code=404, detail="Sandbox verification not found")
        return ok(data={"deleted": verification_id}, message="Sandbox report deleted")
    except HTTPException:
        raise
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to delete sandbox report: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete sandbox report") from exc


@sandbox_router.get("/sandbox/verifications/{verification_id}/events")
async def get_sandbox_events(
    verification_id: str,
    request: Request,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        stored = await asyncio.to_thread(sandbox_service.report, verification_id, principal_for_request(request))
        if stored is not None:
            return ok(data=stored.get("events", []))
        if await asyncio.to_thread(sandbox_service.status, verification_id, principal_for_request(request)) is None:
            raise HTTPException(status_code=404, detail="Sandbox verification not found")
        return ok(data=await asyncio.to_thread(sandbox_service.events, verification_id, principal_for_request(request)))
    except HTTPException:
        raise
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to get sandbox events: {exc}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox events") from exc


@sandbox_router.get("/sandbox/templates/{workflow_id}")
async def get_sandbox_templates(
    workflow_id: str,
    _: Any = Depends(RateLimiter(config, "get_workflow")),
):
    try:
        templates = await asyncio.to_thread(sandbox_service.store.load_templates, workflow_id)
        return ok(data=[template.model_dump() for template in templates])
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to load sandbox templates: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load sandbox templates") from exc


@sandbox_router.put("/sandbox/templates/{workflow_id}")
async def save_sandbox_templates(
    workflow_id: str,
    templates: list[dict],
    _: Any = Depends(RateLimiter(config, "create_workflow")),
):
    try:
        validated = sandbox_service.validate_templates(templates)
        count = await asyncio.to_thread(sandbox_service.store.save_templates, workflow_id, validated)
        return ok(data={"template_count": count}, message="Sandbox templates saved")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    except Exception as exc:
        logger.error(f"Failed to save sandbox templates: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save sandbox templates") from exc

"""Sandbox verification routes shared by internal and external APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from common.util.config_util import get_conf
from orchestrate.core.model.psop import PSOP
from orchestrate.sandbox.models import StubScenario
from orchestrate.sandbox.control_point import SandboxControlPoint
from orchestrate.sandbox.service import SandboxService
from orchestrate.sandbox.store import SandboxStore
from orchestrate.server.middleware import RateLimiter
from orchestrate.server.response_utils import created, get_agent_cards, ok
from orchestrate.server.shared_handlers import SharedHandlers

config = get_conf()
sandbox_service = SandboxService(
    control_point_factory=SandboxControlPoint,
    store=SandboxStore(),
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
        )
        return created(
            data={"verification_id": verification_id, "status": "running"},
            message="Sandbox verification started",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to start sandbox: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start sandbox verification") from exc


@sandbox_router.get("/sandbox/verifications")
async def list_sandbox_reports(
    _: Any = Depends(RateLimiter(config, "list_executions")),
):
    try:
        return ok(data=sandbox_service.store.list_reports())
    except Exception as exc:
        logger.error(f"Failed to list sandbox reports: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list sandbox reports") from exc


@sandbox_router.get("/sandbox/verifications/{verification_id}")
async def get_sandbox_report(
    verification_id: str,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        payload = sandbox_service.store.load_report(verification_id)
        if payload is None:
            status = sandbox_service.status(verification_id)
            if status is None:
                raise HTTPException(status_code=404, detail="Sandbox verification not found")
            return ok(data=status)
        return ok(data=payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get sandbox report: {exc}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox report") from exc


@sandbox_router.delete("/sandbox/verifications/{verification_id}")
async def delete_sandbox_report(
    verification_id: str,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        deleted = sandbox_service.delete_report(verification_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Sandbox verification not found")
        return ok(data={"deleted": verification_id}, message="Sandbox report deleted")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete sandbox report: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete sandbox report") from exc


@sandbox_router.get("/sandbox/verifications/{verification_id}/events")
async def get_sandbox_events(
    verification_id: str,
    _: Any = Depends(RateLimiter(config, "get_execution")),
):
    try:
        stored = sandbox_service.store.load_report(verification_id)
        if stored is not None:
            return ok(data=stored.get("events", []))
        if sandbox_service.status(verification_id) is None:
            raise HTTPException(status_code=404, detail="Sandbox verification not found")
        return ok(data=sandbox_service.events(verification_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get sandbox events: {exc}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox events") from exc


@sandbox_router.get("/sandbox/templates/{workflow_id}")
async def get_sandbox_templates(
    workflow_id: str,
    _: Any = Depends(RateLimiter(config, "get_workflow")),
):
    try:
        templates = sandbox_service.store.load_templates(workflow_id)
        return ok(data=[template.model_dump() for template in templates])
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
        count = sandbox_service.store.save_templates(workflow_id, validated)
        return ok(data={"template_count": count}, message="Sandbox templates saved")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Failed to save sandbox templates: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save sandbox templates") from exc

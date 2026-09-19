from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from loguru import logger
from common.util.config_util import get_conf
from orchestrate.core.model.psop import PSOP
from orchestrate.sandbox.models import SandboxRunReport, StubScenario, StubTemplate
from orchestrate.sandbox.i18n import translate
from orchestrate.sandbox.runner import run_sandbox
from orchestrate.sandbox.store import SandboxStore
from orchestrate.validation.sandbox_validator import SandboxCheckStatus


class SandboxService:
    """Start and observe sandbox verification runs."""

    def __init__(
        self,
        control_point_factory,
        store: SandboxStore | None = None,
    ) -> None:
        self.store = store or SandboxStore()
        self.control_point_factory = control_point_factory
        self._tasks: dict[str, asyncio.Task] = {}
        self._status: dict[str, str] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    async def start(
        self,
        psop: PSOP,
        agent_cards: list[Any],
        scenario: StubScenario = StubScenario.SUCCESS,
        runtime_intent: str = "",
        templates: list[StubTemplate] | None = None,
        lang: str = "zh",
    ) -> str:
        verification_id = str(uuid4())
        self._status[verification_id] = "running"
        self._events[verification_id] = []

        async def run() -> None:
            conf = get_conf()
            scheme = "https" if conf.get("enable_https", "false").lower() == "true" else "http"
            orch_port = conf.get("port", "5001")
            control_point = self.control_point_factory(
                orch_url=f"{scheme}://127.0.0.1:{orch_port}",
                ssl_verify=str(conf.get("client_verify_server", "false")).lower() == "true",
                lang=lang,
            )
            try:
                report = await run_sandbox(
                    psop,
                    agent_cards,
                    control_point,
                    verification_id=verification_id,
                    scenario=scenario,
                    templates=templates,
                    runtime_intent=runtime_intent,
                    lang=lang,
                    event_sink=lambda event: self._events[verification_id].append(event),
                )
                self.store.save_report(report, self._events[verification_id])
            except Exception as exc:
                logger.exception(f"[Sandbox] Verification {verification_id} failed: {exc}")
                report = SandboxRunReport(
                    verification_id=verification_id,
                    workflow_id=psop.id,
                    workflow_name=psop.name,
                    scenario=scenario,
                    verdict=SandboxCheckStatus.FAIL,
                    error=str(exc) or type(exc).__name__,
                    risks=[translate(lang, "report.risk_service_failed")],
                    suggestions=[translate(lang, "report.suggestion_check_log")],
                )
                self.store.save_report(report, self._events[verification_id])
            finally:
                self._status[verification_id] = "completed"
                self._events.pop(verification_id, None)

        task = asyncio.create_task(
            run(),
            name=f"sandbox-{verification_id}",
        )
        self._tasks[verification_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(verification_id, None))
        return verification_id

    async def wait(self, verification_id: str) -> None:
        task = self._tasks.get(verification_id)
        if task is not None:
            await task

    def status(self, verification_id: str) -> dict[str, Any] | None:
        if verification_id not in self._status:
            stored = self.store.load_report(verification_id)
            if stored is None:
                return None
            return {
                "verification_id": verification_id,
                "status": stored.get("status", "completed"),
                "verdict": stored.get("report", {}).get("verdict"),
            }
        return {
            "verification_id": verification_id,
            "status": self._status[verification_id],
            "verdict": self.store.load_report(verification_id).get("report", {}).get("verdict")
            if self.store.load_report(verification_id) else None,
        }

    def events(self, verification_id: str) -> list[dict[str, Any]]:
        return list(self._events.get(verification_id, []))

    def delete_report(self, verification_id: str) -> bool:
        deleted = self.store.delete_report(verification_id)
        if deleted:
            self._status.pop(verification_id, None)
            self._events.pop(verification_id, None)
        return deleted

    def validate_templates(self, payload: Any) -> list[StubTemplate]:
        if not isinstance(payload, list):
            raise ValueError("templates must be a JSON array")
        if len(payload) > 200:
            raise ValueError("templates must contain at most 200 entries")
        try:
            return [StubTemplate.model_validate(item) for item in payload]
        except ValidationError as exc:
            raise ValueError(f"Invalid stub template: {exc}") from exc

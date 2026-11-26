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
from contextlib import suppress
from typing import Any
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError
from common.util.config_util import get_conf
from orchestrate.core.model.psop import PSOP
from orchestrate.sandbox.i18n import translate
from orchestrate.sandbox.models import SandboxRunReport, StubScenario, StubTemplate
from orchestrate.sandbox.runner import run_sandbox
from orchestrate.sandbox.store import SandboxStore
from orchestrate.sandbox.validation import require_instance_workflow
from orchestrate.validation.sandbox_validator import SandboxCheckStatus
from orchestrate.runtime.durable_runs import JobRepository, LeaseLost, TERMINAL


class SandboxService:
    """Local executors coordinated by durable, cross-instance job state."""
    def __init__(self, control_point_factory, store=None, *, max_concurrent_runs=4,
                 run_timeout_seconds=60, lease_seconds=30):
        if max_concurrent_runs < 1 or run_timeout_seconds <= 0:
            raise ValueError("Concurrency and timeout must be positive")
        self.store = store or SandboxStore()
        self.control_point_factory = control_point_factory
        self._max_runs = max_concurrent_runs
        self._lease_seconds = lease_seconds
        self._run_timeout_seconds = run_timeout_seconds
        self._tasks = {}
        self._owner = uuid4().hex
        self._scheduler = None
        self._closing = False

    @property
    def jobs(self):
        return JobRepository(self.store.documents, lease_seconds=self._lease_seconds,
                             max_active=self._max_runs)

    def start_scheduler(self):
        if self._scheduler is None or self._scheduler.done():
            self._closing = False
            self._scheduler = asyncio.create_task(self._schedule(), name="sandbox-scheduler")

    async def _schedule(self):
        from google.protobuf.json_format import ParseDict
        from a2a.types import AgentCard
        while not self._closing:
            try:
                jobs = await asyncio.to_thread(self.jobs.list, None, "sandbox")
                for job in reversed(jobs):
                    if job["status"] == "queued" and job["job_id"] not in self._tasks:
                        value = job["request"]
                        await self.start(PSOP.model_validate(value["psop"]),
                            [ParseDict(card, AgentCard()) for card in value.get("agent_cards", [])],
                            scenario=StubScenario(value["scenario"]), runtime_intent=value["runtime_intent"],
                            templates=[StubTemplate.model_validate(v) for v in value["templates"]],
                            lang=value["lang"], principal=job["principal"],
                            _existing_job=job, identity=value.get("identity"))
                    elif job["status"] in {"preparing", "running"}:
                        await asyncio.to_thread(self.jobs.observe_stale, job["job_id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Sandbox scheduler failed; persisted jobs were retained")
            await asyncio.sleep(.5)

    async def start(self, psop, agent_cards, scenario=StubScenario.SUCCESS,
                    runtime_intent="", templates=None, lang="zh", *, principal="legacy-workspace",
                    idempotency_key=None, _existing_job=None, identity=None):
        # REQ74: role workflows never enter the instance sandbox.
        require_instance_workflow(psop)
        from google.protobuf.json_format import MessageToDict
        request = dict(identity=identity,
                       agent_cards=[MessageToDict(card) for card in agent_cards],
                       psop=psop.model_dump(mode="json"), scenario=str(scenario),
                       runtime_intent=runtime_intent, lang=lang,
                       templates=[v.model_dump(mode="json") for v in (templates or [])])
        jobs = self.jobs
        job = _existing_job or await asyncio.to_thread(jobs.submit, "sandbox", request, principal,
                                      idempotency_key=idempotency_key)
        verification_id = job["job_id"]
        if job["status"] != "queued" or verification_id in self._tasks:
            return verification_id

        async def execute():
            claimed = None
            while claimed is None:
                current = await asyncio.to_thread(jobs.get, verification_id)
                if current is None or current["status"] in TERMINAL:
                    return
                claimed = await asyncio.to_thread(jobs.claim, verification_id, self._owner)
                if claimed is None:
                    if current["status"] != "queued":
                        return  # Another instance accepted the same idempotent request.
                    await asyncio.sleep(0.1)
            fence = claimed["fence"]
            def begin_running():
                with self.store.documents.transaction():
                    current = jobs._owned(verification_id, self._owner, fence)
                    current["status"] = "running"
                    self.store.documents.save("run_jobs", verification_id, current)
            try:
                await asyncio.to_thread(begin_running)
            except LeaseLost:
                return
            execution_task = asyncio.current_task()
            queue = asyncio.Queue(maxsize=2000)
            events = []
            writer_error = []

            async def write_events():
                while True:
                    event = await queue.get()
                    try:
                        if not writer_error:
                            await asyncio.to_thread(jobs.append, verification_id, self._owner, fence, event)
                            events.append(event)
                    except Exception as exc:
                        writer_error.append(exc)
                        execution_task.cancel()
                    finally:
                        queue.task_done()

            async def monitor():
                while True:
                    await asyncio.sleep(min(0.2, self._lease_seconds / 3))
                    try:
                        current = await asyncio.to_thread(jobs.get, verification_id)
                        if (current is None or current["cancel_requested"] or current["status"] in TERMINAL
                                or not await asyncio.to_thread(jobs.renew, verification_id, self._owner, fence)):
                            execution_task.cancel()
                            return
                    except Exception:
                        execution_task.cancel()
                        return

            writer = asyncio.create_task(write_events())
            watcher = asyncio.create_task(monitor())
            status = "completed"
            try:
                if identity is not None:
                    from orchestrate.server.durable_api import validate_frozen_identity
                    if not await asyncio.to_thread(validate_frozen_identity, identity):
                        raise ValueError("Submitting identity is no longer permitted to run sandbox verification")
                conf = get_conf()
                scheme = "https" if str(conf.get("enable_https", "true")).lower() == "true" else "http"
                public_url = conf.get(
                    "orchestration_internal_url") or f"{scheme}://127.0.0.1:{conf.get('port', '5001')}"
                control_point = self.control_point_factory(
                    orch_url=public_url,
                    ssl_verify=str(conf.get("client_verify_server", "true")).lower() == "true", lang=lang)
                async with asyncio.timeout(self._run_timeout_seconds):
                    report = await run_sandbox(psop, agent_cards, control_point,
                        verification_id=verification_id, scenario=scenario, templates=templates,
                        runtime_intent=runtime_intent, lang=lang, event_sink=queue.put_nowait)
            except asyncio.CancelledError:
                status = "cancelled"
                report = self._failure_report(verification_id, psop, scenario, lang,
                                              "Sandbox verification was cancelled")
            except TimeoutError:
                status = "timed_out"
                report = self._failure_report(verification_id, psop, scenario, lang,
                    f"Sandbox verification exceeded {self._run_timeout_seconds:g} seconds")
            except Exception as exc:
                status = "failed"
                report = self._failure_report(verification_id, psop, scenario, lang, str(exc))
            finally:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
                await queue.join()
                writer.cancel()
                with suppress(asyncio.CancelledError):
                    await writer
            if writer_error:
                return  # Durable state remains available; do not publish with a lost fence.

            def complete():
                with self.store.documents.transaction():
                    current = self.store.documents.get("run_jobs", verification_id)
                    if current is None or current.get("deletion_requested"):
                        return
                    if current["status"] == "cancelled":
                        # A pre-dispatch cancellation is already durably fenced.
                        return
                    terminal = "succeeded" if status == "completed" else (
                        "cancelled" if status == "cancelled" else "failed")
                    jobs.finish(verification_id, self._owner, fence, terminal,
                                result={"verification_id": verification_id, "status": status,
                                        "verdict": str(report.verdict)})
                    self.store.save_report(report, events, status=status)
            try:
                await asyncio.to_thread(complete)
            except LeaseLost:
                pass

        task = asyncio.create_task(execute(), name=f"sandbox-{verification_id}")
        self._tasks[verification_id] = task
        task.add_done_callback(lambda done: self._tasks.pop(verification_id, None))
        return verification_id

    async def wait(self, verification_id):
        task = self._tasks.get(verification_id)
        if task is not None:
            await task

    async def cancel_and_delete(self, verification_id, principal=None):
        jobs = self.jobs
        def remove():
            with self.store.documents.transaction():
                current = jobs.get(verification_id, principal)
                if current is not None:
                    jobs.remove(verification_id, principal)
                    self.store.delete_report(verification_id)
                    return True
                # Migrated reports have the existing shared workspace policy.
                if self.store.documents.get("run_jobs", verification_id) is not None:
                    return False
                return self.store.delete_report(verification_id)
        existed = await asyncio.to_thread(remove)
        task = self._tasks.get(verification_id)
        if existed and task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return existed

    async def aclose(self):
        self._closing = True
        if self._scheduler is not None:
            self._scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await self._scheduler
        active = list(self._tasks.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    @staticmethod
    def _failure_report(
        verification_id: str,
        psop: PSOP,
        scenario: StubScenario,
        lang: str,
        error: str,
    ) -> SandboxRunReport:
        return SandboxRunReport(
            verification_id=verification_id,
            workflow_id=psop.id,
            workflow_name=psop.name,
            scenario=scenario,
            verdict=SandboxCheckStatus.FAIL,
            error=error,
            risks=[translate(lang, "report.risk_service_failed")],
            suggestions=[translate(lang, "report.suggestion_check_log")],
        )

    def status(self, verification_id, principal=None):
        jobs = self.jobs
        job = jobs.get(verification_id, principal)
        if job:
            job = jobs.observe_stale(verification_id)
            return {"verification_id": verification_id,
                    "status": (job.get("result") or {}).get("status", job["status"]),
                    "verdict": (job.get("result") or {}).get("verdict"),
                    "as_of_seq": job["last_seq"]}
        if self.store.documents.get("run_jobs", verification_id) is not None:
            return None
        stored = self.store.load_report(verification_id)
        if stored is None:
            return None
        return {"verification_id": verification_id, "status": stored.get("status", "completed"),
                "verdict": stored.get("report", {}).get("verdict")}

    def report(self, verification_id, principal=None):
        if self.status(verification_id, principal) is None:
            return None
        return self.store.load_report(verification_id)

    def list_reports(self, principal=None):
        result = []
        for value in self.store.list_reports():
            if self.status(value["verification_id"], principal) is not None:
                result.append(value)
        return result

    def events(self, verification_id, principal=None):
        with self.store.documents.transaction():
            job = self.jobs.get(verification_id, principal)
            if not job:
                return []
            cursor = job["pruned_through_seq"]
            result = ([{"type": "events_truncated", "data": {"through_seq": cursor}}] if cursor else [])
            while cursor < job["last_seq"]:
                _, rows = self.jobs.read_events(verification_id, principal, cursor)
                if not rows:
                    break
                result.extend(row["event"] for row in rows)
                cursor = rows[-1]["seq"]
            return result

    def delete_report(self, verification_id):
        with self.store.documents.transaction():
            removed = self.store.delete_report(verification_id)
            if removed and self.jobs.get(verification_id) is not None:
                self.jobs.remove(verification_id, None)
            return removed

    def validate_templates(self, payload: Any) -> list[StubTemplate]:
        if not isinstance(payload, list):
            raise ValueError("templates must be a JSON array")
        if len(payload) > 200:
            raise ValueError("templates must contain at most 200 entries")
        try:
            return [StubTemplate.model_validate(item) for item in payload]
        except ValidationError as exc:
            raise ValueError(f"Invalid stub template: {exc}") from exc

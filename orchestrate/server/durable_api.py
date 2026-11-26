# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Submit once, observe anywhere: explicit durable execution API.

Unlike legacy single-instance SSE, disconnecting this subscription never cancels
an execution. Unknown Host outcomes are retained for reconciliation, not retried.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import time
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from google.protobuf.json_format import MessageToDict, ParseDict
from a2a.types import AgentCard
from loguru import logger
from pydantic import BaseModel, Field

from common.util.config_util import get_conf
from orchestrate.core.model.psop import PSOP
from orchestrate.persistence import current_context
from orchestrate.persistence.errors import StorageError
from orchestrate.runtime.durable_runs import JobRepository, LeaseLost, CursorExpired, TERMINAL, run_snapshot
from orchestrate.runtime.exec_engine import OrchestrationEngine
from orchestrate.runtime.instance_projection import (
    ResolutionRequest,
    bind_resolution_identity,
    configured_authorized_instances,
    configured_execution_scope,
)
from orchestrate.server.response_utils import ok, get_agent_cards
from orchestrate.server.storage_error_response import storage_http_exception

run_router = APIRouter()

#: Consecutive storage failures a lease monitor tolerates before it cancels the
#: run it is guarding. One transient blip must not kill a healthy execution.
LEASE_MONITOR_MAX_FAILURES = 3


def principal_for_request(request):
    user = getattr(request.state, "user_identity", None)
    machine = getattr(request.state, "machine_identity", None)
    if user is not None:
        return "user:" + (getattr(user, "subject_id", None) or user.username)
    if machine is not None:
        subject_id = getattr(machine, "subject_id", None)
        return ("user:" + subject_id) if subject_id else ("machine:" + machine.subject)
    raise HTTPException(401, "Verified identity required")


def _identity_snapshot(request):
    identity = getattr(request.state, "user_identity", None) or getattr(request.state, "machine_identity", None)
    value = {
        "principal": principal_for_request(request),
        "role": getattr(identity, "role", None),
        "subject_id": getattr(identity, "subject_id", None),
    }
    conf = get_conf()
    if value["principal"].startswith("machine:"):
        from orchestrate.server.external_auth import external_auth_mode, api_token

        mode = external_auth_mode(conf)
        if mode == "custom":
            raise HTTPException(503, "Custom authentication has no durable identity validation contract")
        value["provider_mode"] = mode
        if mode == "bearer":
            value["credential_revision"] = hashlib.sha256(api_token(conf).encode()).hexdigest()
    elif not value["subject_id"]:
        value["credential_revision"] = hashlib.sha256(str(conf.get("access_password", "")).encode()).hexdigest()
    return value


class DurableRunRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=10000)
    workflow_id: str | None = Field(None, max_length=256)
    target_agent: str | None = Field(None, max_length=256)
    lang: str = Field("zh", pattern="^(zh|en)$")
    scope: str | None = Field(None, max_length=512)
    authorized_instance_ids: list[str] | None = Field(None, max_length=1000)


class RunCoordinator:
    def __init__(
        self,
        documents,
        *,
        engine_factory=OrchestrationEngine,
        poll_seconds=0.25,
        lease_seconds=30,
        max_active=16,
        deadline_seconds=3600,
        history_repository=None,
    ):
        self.repo = JobRepository(documents, lease_seconds=lease_seconds, max_active=max_active)
        self.owner = uuid4().hex
        self.engine_factory = engine_factory
        self.poll_seconds = poll_seconds
        self.deadline_seconds = deadline_seconds
        self.history_repository = history_repository
        self.tasks = {}
        self.scheduler = None
        self.closing = False

    def start(self):
        if self.scheduler is None or self.scheduler.done():
            self.closing = False
            self.scheduler = asyncio.create_task(self._schedule(), name="durable-run-scheduler")

    async def _schedule(self):
        while not self.closing:
            try:
                for job in reversed(await asyncio.to_thread(self.repo.list, None, "execution")):
                    if job["status"] in {"preparing", "dispatching", "running"}:
                        await asyncio.to_thread(self.observe, job["job_id"])
                    if job["status"] == "queued" and job["job_id"] not in self.tasks:
                        claimed = await asyncio.to_thread(self.repo.claim, job["job_id"], self.owner)
                        if claimed is not None:
                            task = asyncio.create_task(self._execute(claimed), name="durable-" + job["job_id"])
                            self.tasks[job["job_id"]] = task
                            task.add_done_callback(lambda _task, key=job["job_id"]: self.tasks.pop(key, None))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Durable scheduler failed; no task was silently requeued")
            await asyncio.sleep(self.poll_seconds)

    def submit(self, request, principal, idempotency_key=None):
        with self.repo.documents.transaction():
            job = self.repo.submit("execution", request, principal, idempotency_key=idempotency_key)
            if self.history_repository is not None and self.history_repository.get(job["job_id"]) is None:
                self._save_history(job)
            return job

    def _save_history(self, job):
        if self.history_repository is None or job.get("deletion_requested"):
            return
        from orchestrate.core.model.execution_record import ExecutionRecord, ExecutionStatus

        result = job.get("result") or {}
        psop = result.get("final_psop") or job.get("execution_psop") or job["request"].get("psop") or {}
        resolution = result.get("resolution") or job.get("resolution") or {}
        mapping = {
            "succeeded": ExecutionStatus.SUCCESS,
            "failed": ExecutionStatus.FAILED,
            "cancelled": ExecutionStatus.STOPPED,
            "reconciliation_required": ExecutionStatus.STOPPED,
        }
        kwargs = dict(
            execution_id=job["job_id"],
            psop_id=psop.get("id") or "dispatch-" + job["job_id"],
            psop_name=psop.get("name") or job["request"]["intent"][:80],
            started_at=datetime.fromtimestamp(job["created_at"], timezone.utc),
            completed_at=(
                datetime.fromtimestamp(job["updated_at"], timezone.utc) if job["status"] in TERMINAL else None
            ),
            status=mapping.get(job["status"], ExecutionStatus.RUNNING),
            final_psop=psop or None,
            events=result.get("events", []),
            error=job.get("error"),
        )
        for key in (
            "catalog_version",
            "config_version",
            "policy_version",
            "execution_scope",
            "bindings",
            "card_fingerprints",
            "resolution_snapshot",
            "template_fingerprint",
            "snapshot_fingerprint",
        ):
            if key in resolution:
                kwargs[key] = resolution[key]
        self.history_repository.save(ExecutionRecord(**kwargs))

    def cancel(self, job_id, principal):
        with self.repo.documents.transaction():
            job = self.repo.cancel(job_id, principal)
            if job is not None:
                self._save_history(job)
            return job

    def observe(self, job_id):
        with self.repo.documents.transaction():
            job = self.repo.observe_stale(job_id)
            if job is not None and job["status"] == "reconciliation_required":
                self._save_history(job)
            return job

    def _finish(self, job_id, fence, status, result, error, terminal_event=None):
        with self.repo.documents.transaction():
            if terminal_event is not None:
                self.repo.append(job_id, self.owner, fence, terminal_event)
            job = self.repo.finish(job_id, self.owner, fence, status, result, error)
            self._save_history(job)
            return job

    async def _execute(self, job):
        job_id, fence = job["job_id"], job["fence"]
        sent = False
        terminal = None
        terminal_error = None
        collected = []
        final_psop = job["request"].get("psop")
        resolution = None
        terminal_event = None
        runner = asyncio.current_task()

        async def monitor():
            # A transient storage blip must not cancel a healthy run: tolerate a
            # few consecutive failures before giving up, and always leave a trace.
            failures = 0
            while True:
                await asyncio.sleep(max(min(self.repo.lease_seconds / 3, 1), 0.05))
                try:
                    current = await asyncio.to_thread(self.repo.get, job_id)
                    if current is None or not await asyncio.to_thread(self.repo.renew, job_id, self.owner, fence):
                        runner.cancel()
                        return
                    if current["cancel_requested"]:
                        runner.cancel()
                        return
                    failures = 0
                except Exception as error:
                    failures += 1
                    if failures >= LEASE_MONITOR_MAX_FAILURES:
                        logger.warning(
                            "Lease monitor gave up after %s consecutive storage failures: %s", failures, error)
                        runner.cancel()
                        return
                    logger.warning("Lease monitor retry %s/%s: %s", failures, LEASE_MONITOR_MAX_FAILURES, error)

        watchdog = asyncio.create_task(monitor())
        try:
            spec = job["request"]
            frozen_identity = spec.get("identity", {})
            if not await asyncio.to_thread(validate_frozen_identity, frozen_identity):
                raise ValueError("Submitting identity is no longer permitted to execute")
            cards = [ParseDict(card, AgentCard()) for card in spec["agent_cards"]]
            if not cards:
                raise ValueError("No agent cards available")
            request = ResolutionRequest.model_validate(spec["resolution_request"])
            request._verified_caller_id = spec["verified_caller_id"]
            engine = self.engine_factory(
                cards,
                target_agent=spec["target_agent"],
                lang=spec["lang"],
                select_template=spec.get("select_template", True),
            )
            psop = PSOP.model_validate(spec["psop"]) if spec.get("psop") else None

            async def dispatch_guard(envelope):
                nonlocal sent
                if not await asyncio.to_thread(validate_frozen_identity, frozen_identity):
                    raise ValueError("Submitting identity is no longer permitted to dispatch")
                await asyncio.to_thread(self.repo.mark_dispatch, job_id, self.owner, fence, envelope)
                sent = True

            async def observe_transport(value):
                await asyncio.to_thread(self.repo.observe_transport, job_id, self.owner, fence, value)

            source = engine.events(
                spec["intent"],
                psop=psop,
                resolution_request=request,
                execution_id=job_id,
                dispatch_guard=dispatch_guard,
                transport_observer=observe_transport,
            )
            try:
                async with asyncio.timeout(self.deadline_seconds):
                    async for event in source:
                        if event.get("type") == "start" and event.get("data", {}).get("phase") == "dispatching":
                            # The generator cannot advance to stream_message until this
                            # transaction commits. Future owners never repeat this attempt.
                            if not sent:
                                raise ValueError("Execution engine bypassed the durable dispatch guard")
                        if event.get("type") in {"complete", "cancelled", "error"}:
                            terminal_event = event
                        else:
                            await asyncio.to_thread(self.repo.append, job_id, self.owner, fence, event)
                        collected.append(event)
                        collected = collected[-1000:]
                        data = event.get("data", {})
                        if event.get("type") == "psop_update":
                            final_psop = data.get("psop", final_psop)
                        elif event.get("type") == "resolution":
                            resolution = data
                        elif event.get("type") == "complete":
                            terminal = "succeeded"
                        elif event.get("type") == "cancelled":
                            terminal = "cancelled"
                        elif event.get("type") == "error" and terminal is None:
                            terminal = (
                                "reconciliation_required"
                                if sent and data.get("dispatch_outcome") == "unknown"
                                else "failed"
                            )
                            terminal_error = data.get("error", "Execution failed")
            finally:
                with suppress(Exception):
                    await source.aclose()
            if terminal is None:
                terminal = "reconciliation_required" if sent else "failed"
                terminal_error = "Host stream ended without a confirmed terminal outcome"
        except LeaseLost:
            return
        except asyncio.CancelledError:
            terminal = "reconciliation_required" if sent else "cancelled"
            terminal_error = (
                "Execution interrupted; remote outcome is unknown" if sent else "Execution cancelled before dispatch"
            )
        except Exception as exc:
            terminal = "reconciliation_required" if sent else "failed"
            terminal_error = str(exc)
        finally:
            watchdog.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog
        if terminal:
            result = {
                "execution_id": job_id,
                "psop_id": (final_psop or {}).get("id"),
                "psop_name": (final_psop or {}).get("name"),
                "final_psop": final_psop,
                "resolution": resolution,
                "events": collected,
            }
            try:
                await asyncio.to_thread(self._finish, job_id, fence, terminal, result, terminal_error, terminal_event)
            except LeaseLost:
                # Another instance observes the expired owner and records unknown.
                pass
            except Exception:
                logger.exception("Failed to persist terminal run state; lease recovery retains the run")

    async def aclose(self):
        self.closing = True
        if self.scheduler:
            self.scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await self.scheduler
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


_coordinators = {}


def get_run_coordinator():
    documents = current_context().documents
    key = id(documents)
    coordinator = _coordinators.get(key)
    if coordinator is None:
        conf = get_conf()
        coordinator = RunCoordinator(
            documents,
            lease_seconds=float(conf.get("execution_lease_seconds", 30)),
            max_active=int(conf.get("execution_max_active", 16)),
            deadline_seconds=float(conf.get("execution_deadline_seconds", 3600)),
            history_repository=current_context().executions,
        )
        _coordinators[key] = coordinator
    coordinator.start()
    return coordinator


async def close_durable_runs():
    for coordinator in list(_coordinators.values()):
        await coordinator.aclose()
    _coordinators.clear()


async def submit_execution(
    request,
    *,
    agent_cards,
    intent,
    target_agent=None,
    lang=None,
    psop=None,
    resolution_request=None,
    idempotency_key=None,
    select_template=True,
):
    conf = get_conf()
    identity = _identity_snapshot(request)
    resolution = resolution_request or ResolutionRequest()
    bind_resolution_identity(resolution, request)
    allowed_at_acceptance = set(configured_authorized_instances())
    if resolution.authorized_instance_ids is None:
        resolution.authorized_instance_ids = sorted(allowed_at_acceptance)
    elif set(resolution.authorized_instance_ids) - allowed_at_acceptance:
        raise HTTPException(403, "Requested instances exceed server authorization")
    else:
        resolution.authorized_instance_ids = sorted(set(resolution.authorized_instance_ids))
    if resolution.scope is None:
        resolution.scope = configured_execution_scope()
    body = await request.body()
    try:
        canonical_body = json.loads(body) if body else None
    except ValueError:
        canonical_body = hashlib.sha256(body).hexdigest()
    public_request = {
        "method": request.method,
        "path": request.url.path,
        "query": sorted((k, v) for k, v in request.query_params.multi_items() if k != "request_key"),
        "body": canonical_body,
    }
    spec = {
        "_idempotency_payload": public_request,
        "intent": intent,
        "target_agent": target_agent or conf.get("workflow_host_agent_name", "Host Agent"),
        "lang": lang or "zh",
        "psop": psop.model_dump(mode="json") if psop else None,
        "agent_cards": [MessageToDict(card) for card in agent_cards],
        "resolution_request": resolution.model_dump(mode="json"),
        "verified_caller_id": resolution._verified_caller_id,
        "identity": identity,
        "select_template": select_template,
    }
    coordinator = get_run_coordinator()
    job = await asyncio.to_thread(coordinator.submit, spec, identity["principal"], idempotency_key)
    return job


@run_router.post("/runs", status_code=202)
async def submit_run(
    body: DurableRunRequest, request: Request, idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    try:
        psop = await asyncio.to_thread(current_context().psops.get, body.workflow_id) if body.workflow_id else None
        if body.workflow_id and psop is None:
            raise HTTPException(404, "Workflow not found")
        job = await submit_execution(
            request,
            agent_cards=await get_agent_cards(),
            intent=body.intent,
            target_agent=body.target_agent,
            lang=body.lang,
            psop=psop,
            resolution_request=ResolutionRequest(
                scope=body.scope, authorized_instance_ids=body.authorized_instance_ids
            ),
            idempotency_key=idempotency_key,
        )
        return {
            "code": 202,
            "status": "success",
            "data": run_snapshot(job),
            "message": "Execution accepted; disconnecting does not cancel it",
        }
    except StorageError as exc:
        raise storage_http_exception(exc) from exc


@run_router.get("/runs")
async def list_runs(request: Request):
    try:
        repo = get_run_coordinator().repo
        jobs = await asyncio.to_thread(repo.list, principal_for_request(request), "execution")
        return ok(data=[run_snapshot(j) for j in jobs])
    except StorageError as exc:
        raise storage_http_exception(exc) from exc


@run_router.get("/runs/{job_id}")
async def get_run(job_id: str, request: Request):
    try:
        repo = get_run_coordinator().repo
        principal = principal_for_request(request)
        job = await asyncio.to_thread(repo.get, job_id, principal)
        if job is None:
            raise HTTPException(404, "Execution not found")
        await asyncio.to_thread(get_run_coordinator().observe, job_id)
        job = await asyncio.to_thread(repo.get, job_id, principal)
        if job is None:
            raise HTTPException(404, "Execution not found")
        return ok(data=run_snapshot(job))
    except StorageError as exc:
        raise storage_http_exception(exc) from exc


@run_router.post("/runs/{job_id}/cancel", status_code=202)
async def cancel_run(job_id: str, request: Request):
    try:
        repo = get_run_coordinator().repo
        job = await asyncio.to_thread(get_run_coordinator().cancel, job_id, principal_for_request(request))
        if job is None:
            raise HTTPException(404, "Execution not found")
        return ok(data=run_snapshot(job), message="Cancellation requested; remote stop may require reconciliation")
    except StorageError as exc:
        raise storage_http_exception(exc) from exc


async def durable_event_response(request, job_id, after=0):
    repo = get_run_coordinator().repo
    principal = principal_for_request(request)
    try:
        job, _ = await asyncio.to_thread(repo.read_events, job_id, principal, after)
    except StorageError as exc:
        raise storage_http_exception(exc) from exc
    if job is None:
        raise HTTPException(404, "Execution not found")

    async def stream():
        cursor = after
        yield "data: " + json.dumps(
            {"type": "execution_accepted", "data": {"execution_id": job_id, "lifecycle": "durable", "as_of_seq": after}}
        ) + "\n\n"
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            try:
                # Re-enter shared authentication for every page; a revoked token
                # cannot keep an established subscription alive indefinitely.
                from orchestrate.server.auth import require_session_identity

                conf = get_conf()
                if str(conf.get("external.auth.mode", "user")) in {"user", "auto"} or not request.url.path.startswith(
                    "/api/v1/"
                ):
                    require_session_identity(request, allow_cookie=not request.url.path.startswith("/api/v1/"))
                else:
                    from orchestrate.server.external_auth import authenticate_external

                    refreshed = await authenticate_external(request, conf)
                    if "machine:" + refreshed.subject != principal:
                        raise HTTPException(403, "Execution identity changed")
                current, rows = await asyncio.to_thread(repo.read_events, job_id, principal, cursor)
                if current is None:
                    break
                for row in rows:
                    cursor = row["seq"]
                    yield f"id: {job_id}:{cursor}\ndata: {json.dumps(row['event'], ensure_ascii=False)}\n\n"
                if cursor == current["last_seq"] and (
                    current["status"] in TERMINAL or current["status"] == "reconciliation_required"
                ):
                    break
            except (StorageError, HTTPException) as exc:
                # Headers have already been sent: explicit protocol error, never
                # pretend a gap or unavailable authentication is an empty tail.
                yield "event: stream_error\ndata: " + json.dumps(
                    {"error": "Subscription unavailable; reload the execution snapshot"}
                ) + "\n\n"
                break
            if time.monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Execution-ID": job_id,
            "X-Execution-Lifecycle": "durable",
        },
    )


@run_router.get("/runs/{job_id}/events")
async def run_events(
    job_id: str, request: Request, after_seq: int = 0, last_event_id: str | None = Header(None, alias="Last-Event-ID")
):
    if last_event_id:
        prefix, separator, raw = last_event_id.rpartition(":")
        if separator != ":" or prefix != job_id or not raw.isdecimal():
            raise HTTPException(400, "Event cursor belongs to a different execution")
        after_seq = int(raw)
    return await durable_event_response(request, job_id, after_seq)


def history_visible(execution_id, request):
    if not execution_id:
        return True
    job = current_context().documents.get("run_jobs", execution_id)
    if job is None:
        return True  # Existing history belongs to the legacy shared workspace.
    return not job.get("deletion_requested") and job["principal"] == principal_for_request(request)


def remove_history_job(execution_id, request):
    from orchestrate.core.persistence import WorkflowStorage

    WorkflowStorage._validate_execution_id(execution_id)
    repo = JobRepository(current_context().documents)
    job = repo.documents.get("run_jobs", execution_id)
    if job is not None:
        if not repo.remove(execution_id, principal_for_request(request)):
            raise HTTPException(404, "Execution not found")


def validate_frozen_identity(identity):
    if identity.get("subject_id"):
        from orchestrate.server.auth import validate_job_identity

        return validate_job_identity(identity["subject_id"], identity.get("role"))
    conf = get_conf()
    if identity.get("principal", "").startswith("machine:"):
        from orchestrate.server.external_auth import external_auth_mode, external_auth_configured, api_token

        mode = external_auth_mode(conf)
        return (
            mode == identity.get("provider_mode")
            and external_auth_configured(conf)
            and (
                mode != "bearer"
                or hashlib.sha256(api_token(conf).encode()).hexdigest() == identity.get("credential_revision")
            )
        )
    return (
        identity.get("credential_revision") == hashlib.sha256(str(conf.get("access_password", "")).encode()).hexdigest()
    )

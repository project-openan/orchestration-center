# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Authenticated, finite HTTP ingestion and read-only execution replay."""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hmac
import json
import os
import re
import rfc8785
from threading import Lock
import time
from typing import Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from loguru import logger

from orchestrate.persistence.execution_observation import (
    FINISH, GAP, PREFIX, START, ObservationConflict, encoded, observation_store,
    observation_enabled as enabled,
)

router = APIRouter()
INGEST_PATH = "/api/v1/execution-events"
MAX_BYTES = 1024 * 1024
MAX_EVENT_BYTES = 64 * 1024
MAX_SEQUENCE = 2**53 - 1
TRACE_PARENT = re.compile(r"00-(?!0{32})[0-9a-f]{32}-(?!0{16})[0-9a-f]{16}-[0-9a-f]{2}")
TYPE_NAMES = {
    "execution.started", "execution.finished", "execution.gap.declared",
    "step.started", "step.finished", "task.started", "task.progressed", "task.finished",
}
ENVELOPE_FIELDS = {"specversion", "id", "source", "type", "subject", "time",
                   "datacontenttype", "dataschema", "seq", "data", "traceparent", "tracestate"}
OUTCOMES = {"succeeded", "failed", "cancelled"}
PHASES = {
    "negotiation": {"requested", "resolved", "failed"},
    "agent_call": {"sent", "received", "failed"},
}
_rate_lock = Lock()
_requests = {}


class InvalidEvent(ValueError):
    def __init__(self, code, index=None, status=422):
        super().__init__(code)
        self.code = code
        self.index = index
        self.status = status


@lru_cache(maxsize=4)
def _hosts(raw):
    if not raw:
        return {}
    hosts = json.loads(raw)
    if not isinstance(hosts, dict) or not all(
        re.fullmatch(r"urn:openan:host:[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", source)
        and isinstance(policy, dict)
        and set(policy) == {"token_env", "psop_ids"}
        and isinstance(policy["token_env"], str)
        and re.fullmatch(r"[A-Z_][A-Z_0-9]*", policy["token_env"])
        and isinstance(policy["psop_ids"], list)
        and policy["psop_ids"]
        and all(_bounded_string(psop_id, 128) for psop_id in policy["psop_ids"])
        for source, policy in hosts.items()
    ):
        raise ValueError("Invalid execution observation host configuration")
    if len({policy["token_env"] for policy in hosts.values()}) != len(hosts):
        raise ValueError("Execution observation hosts must use independent credentials")
    return hosts


def reporting_source(identity):
    """Use the existing account or an independently identified integration."""
    from hashlib import sha256
    from common.util.config_util import get_conf
    from orchestrate.server.external_auth import external_auth_mode

    mode = external_auth_mode(get_conf())
    if identity is None or mode not in {"user", "custom"}:
        return None
    subject = identity.subject
    return "urn:openan:host:identity-" + sha256(f"{mode}:{subject}".encode()).hexdigest()


async def _authenticate(request):
    hosts = _hosts(os.environ.get("OPENAN_EXECUTION_HOSTS", ""))
    auth = request.headers.getlist("authorization")
    parts = auth[0].split() if len(auth) == 1 else []
    if len(parts) == 2 and parts[0].lower() == "bearer":
        match = []
        for source, policy in hosts.items():
            token = os.environ.get(policy["token_env"], "").encode()
            if len(token) >= 32 and hmac.compare_digest(parts[1].encode(), token):
                match.append((source, frozenset(policy["psop_ids"])))
        if len(match) == 1:
            return match[0]
        if match:
            raise InvalidEvent("INVALID_HOST_CREDENTIAL", status=401)

    from common.util.config_util import get_conf
    from orchestrate.server.external_auth import authenticate_external
    try:
        identity = await authenticate_external(request, get_conf())
    except HTTPException as exc:
        raise InvalidEvent("INVALID_HOST_CREDENTIAL", status=exc.status_code) from None
    source = reporting_source(identity)
    if source is None:
        raise InvalidEvent("INVALID_HOST_CREDENTIAL", status=403)
    # The external PSOP catalog is shared by authenticated callers; PSOP visibility and
    # reporting authorization belong to the permission model, not to this transport check.
    return source, frozenset({"*"})


def _secure_transport(request) -> bool:
    """TLS is required, including when it is terminated by a trusted reverse proxy."""
    if request.url.scheme == "https":
        return True
    client = request.client.host if request.client else ""
    if client in {"127.0.0.1", "::1"}:
        return True
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if forwarded == "https" and client:
        from common.util.config_util import get_conf

        trusted = str(get_conf().get("forwarded_allow_ips", "127.0.0.1"))
        allowed = {item.strip() for item in trusted.split(",") if item.strip()}
        if "*" in allowed or client in allowed:
            return True
    return False


def _rate_limit(source):
    now = time.monotonic()
    limit = int(os.environ.get("OPENAN_EXECUTION_BATCHES_PER_SECOND", "20"))
    with _rate_lock:
        stamps = _requests.setdefault(source, deque())
        while stamps and stamps[0] <= now - 1:
            stamps.popleft()
        if len(stamps) >= limit:
            raise InvalidEvent("RATE_LIMIT", status=429)
        stamps.append(now)


def _uuid(value, version=None):
    try:
        parsed = UUID(value)
        return value == str(parsed) and (version is None or parsed.version == version)
    except (ValueError, TypeError, AttributeError):
        return False


def _bounded_string(value, length):
    return isinstance(value, str) and 0 < len(value) <= length


def _check_event(event, index, source):
    if not isinstance(event, dict):
        raise InvalidEvent("INVALID_EVENT", index)
    if event.get("source") != source:
        raise InvalidEvent("SOURCE_MISMATCH", index, 403)
    seq = event.get("seq")
    full_type = event.get("type")
    if (set(event) - ENVELOPE_FIELDS or event.get("specversion") != "1.0" or not _uuid(event.get("id"))
            or not _uuid(event.get("subject"), 4)
            or not isinstance(seq, str) or not re.fullmatch(r"[1-9][0-9]{0,15}", seq)
            or int(seq) > MAX_SEQUENCE or not isinstance(full_type, str)
            or not full_type.startswith(PREFIX) or not full_type.endswith(".v1")
            or full_type[len(PREFIX):-3] not in TYPE_NAMES
            or event.get("datacontenttype", "application/json") != "application/json"
            or not isinstance(event.get("data"), dict)):
        raise InvalidEvent("INVALID_EVENT_ENVELOPE", index)
    if not _bounded_string(event.get("time"), 40):
        raise InvalidEvent("INVALID_EVENT_TIME", index)
    try:
        timestamp = datetime.fromisoformat(event["time"])
        if (timestamp.utcoffset() is None or "T" not in event["time"]
                or timestamp > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError
    except ValueError:
        raise InvalidEvent("INVALID_EVENT_TIME", index) from None
    if "traceparent" in event and (not isinstance(event["traceparent"], str)
                                   or not TRACE_PARENT.fullmatch(event["traceparent"])):
        raise InvalidEvent("INVALID_TRACE_CONTEXT", index)
    if "tracestate" in event and ("traceparent" not in event or not _bounded_string(event["tracestate"], 512)
                                  or not re.fullmatch(r"[ -~]+", event["tracestate"])):
        raise InvalidEvent("INVALID_TRACE_CONTEXT", index)
    try:
        if len(encoded(event).encode()) > MAX_EVENT_BYTES:
            raise InvalidEvent("EVENT_TOO_LARGE", index, 413)
    except (UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise InvalidEvent("INVALID_EVENT", index) from None
    data = event["data"]
    if (seq == "1") != (full_type == START):
        raise InvalidEvent("INVALID_START_SEQUENCE", index)
    kind = full_type[len(PREFIX):-3]
    _check_payload(kind, data, index)


def _check_payload(kind, data, index):
    allowed = {"summary", "result", "error"}
    if kind == "execution.started":
        allowed = {"psop_id", "psop_revision", "business_ref"}
        revision = data.get("psop_revision")
        if (not _bounded_string(data.get("psop_id"), 128)
                or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision)
                or ("business_ref" in data and not _bounded_string(data["business_ref"], 128))):
            raise InvalidEvent("INVALID_EXECUTION_START", index)
    elif kind == "execution.gap.declared":
        allowed = {"reason_code"}
        if data.get("reason_code") not in ("permanent_rejection", "spool_loss"):
            raise InvalidEvent("INVALID_GAP_DECLARATION", index)
    elif kind == "execution.finished":
        allowed |= {"outcome", "capture_status"}
        if "capture_status" in data and data["capture_status"] != "degraded":
            raise InvalidEvent("INVALID_CAPTURE_STATUS", index)
    else:
        allowed.add("step_ref")
        step = data.get("step_ref")
        if not isinstance(step, str) or not re.fullmatch(r"s(?:0|[1-9][0-9]{0,7})", step):
            raise InvalidEvent("INVALID_STEP_REF", index)
        if kind.startswith("task."):
            allowed |= {"task_ref", "task_id", "attempt", "interaction"}
            if kind == "task.progressed":
                allowed.add("input_summary")
            task_ref = data.get("task_ref")
            attempt = data.get("attempt")
            if (not isinstance(task_ref, str) or not re.fullmatch(step + r"/t(?:0|[1-9][0-9]{0,7})", task_ref)
                    or not _uuid(data.get("task_id")) or type(attempt) is not int
                    or not 1 <= attempt <= 65535):
                raise InvalidEvent("INVALID_TASK_IDENTITY", index)
            if "interaction" in data:
                interaction = data["interaction"]
                if (kind != "task.progressed" or not isinstance(interaction, dict)
                        or not isinstance(interaction.get("kind"), str)
                        or not isinstance(interaction.get("phase"), str)
                        or interaction["phase"] not in PHASES.get(interaction["kind"], ())
                        or set(interaction) - {"kind", "phase", "interaction_id"}
                        or ("interaction_id" in interaction and not _bounded_string(interaction["interaction_id"], 128))):
                    raise InvalidEvent("INVALID_INTERACTION", index)
        if kind.endswith(".finished"):
            allowed.add("outcome")
    if kind.endswith(".finished"):
        outcome = data.get("outcome")
        if not isinstance(outcome, str) or (outcome not in OUTCOMES
                                             and not (kind == "step.finished" and outcome == "skipped")):
            raise InvalidEvent("INVALID_OUTCOME", index)
    if (set(data) - allowed or ("summary" in data and not _bounded_string(data["summary"], 2048))
            or ("input_summary" in data and not _bounded_string(data["input_summary"], 2048))
            or ("error" in data and (not isinstance(data["error"], dict)
                                   or set(data["error"]) - {"code", "message"}
                                   or not all(_bounded_string(value, 1024) for value in data["error"].values())))
            or ("result" in data and (not isinstance(data["result"], dict)
                                    or set(data["result"]) - {"summary", "outputs"}
                                    or ("outputs" in data["result"] and not isinstance(data["result"]["outputs"], dict))))):
        raise InvalidEvent("INVALID_EVENT_DATA", index)


def _unique_keys(pairs):
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError("Duplicate JSON object key")
    return data


def _reject_number(number):
    raise ValueError(f"Non-finite JSON number: {number}")


def _problem(code, status, event_index=None, **fields):
    body = {"type": "about:blank", "title": code.replace("_", " ").title(),
            "status": status, "code": code, **fields}
    if event_index is not None:
        body["event_index"] = event_index
    headers = {"Retry-After": "1"} if status in (429, 503) else None
    if status == 401:
        headers = {"WWW-Authenticate": "Bearer"}
    return JSONResponse(body, status, headers=headers, media_type="application/problem+json")


@router.post(INGEST_PATH)
async def ingest_execution_events(request: Request):
    try:
        if not _secure_transport(request):
            raise InvalidEvent("HTTPS_REQUIRED", status=403)
        source, allowed_psops = await _authenticate(request)
        _rate_limit(source)
        media = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media not in {"application/cloudevents+json", "application/cloudevents-batch+json"}:
            raise InvalidEvent("UNSUPPORTED_MEDIA_TYPE", status=415)
        received = bytearray()
        async for chunk in request.stream():
            if len(received) + len(chunk) > MAX_BYTES:
                raise InvalidEvent("BATCH_TOO_LARGE", status=413)
            received.extend(chunk)
        try:
            payload = json.loads(received, object_pairs_hook=_unique_keys, parse_constant=_reject_number)
        except (ValueError, RecursionError):
            raise InvalidEvent("INVALID_JSON", status=400) from None
        events = [payload] if media == "application/cloudevents+json" else payload
        if not isinstance(events, list) or not events:
            raise InvalidEvent("INVALID_BATCH", status=400)
        if len(events) > 100:
            raise InvalidEvent("BATCH_TOO_LARGE", status=413)
        for index, event in enumerate(events):
            _check_event(event, index, source)
            if event["subject"] != events[0]["subject"]:
                raise InvalidEvent("MIXED_EXECUTIONS", index, 400)
        header = request.headers.get("traceparent")
        if any(event.get("traceparent") and event["traceparent"] != header for event in events):
            raise InvalidEvent("TRACE_CONTEXT_MISMATCH")
        state = request.headers.get("tracestate")
        if any(event.get("tracestate") and event["tracestate"] != state for event in events):
            raise InvalidEvent("TRACE_CONTEXT_MISMATCH")
        return await anyio.to_thread.run_sync(lambda: observation_store().ingest(events, allowed_psops))
    except InvalidEvent as exc:
        return _problem(exc.code, exc.status, exc.index)
    except ObservationConflict as exc:
        status = {"OWNER_MISMATCH": 403, "PSOP_FORBIDDEN": 403, "EXECUTION_CLOSED": 410,
                  "REVISION_NOT_FOUND": 422, "INVALID_STEP_REF": 422,
                  "INVALID_TASK_REF": 422}.get(exc.code, 409)
        return _problem(exc.code, status, exc.index, **exc.fields)
    except Exception as exc:
        logger.warning("Observation ingest failed ({})", type(exc).__name__)
        return _problem("OBSERVATION_UNAVAILABLE", 503)


def observed_detail(execution_id):
    return observation_store().detail(execution_id) if enabled() else None


def merge_observed_records(records):
    if not enabled():
        return records
    observed = observation_store().list_runs()
    ids = {record["execution_id"] for record in observed}
    return sorted([*observed, *(record for record in records if record["execution_id"] not in ids)],
                  key=lambda record: record.get("started_at") or "", reverse=True)


@router.get("/api/v1/executions/{execution_id}/events")
@router.get("/rest/v1/orchestrate/executions/{execution_id}/events")
def get_execution_events(execution_id: str, after_cursor: int = Query(0, ge=0, le=MAX_SEQUENCE),
                         limit: int = Query(100, ge=1, le=500),
                         through_cursor: int | None = Query(None, ge=0, le=MAX_SEQUENCE),
                         view: Literal["raw", "timeline"] = "raw"):
    rows = (observation_store().events(
        execution_id, after_cursor, limit, through_cursor, timeline=view == "timeline",
    ) if enabled() else None)
    if rows is None:
        raise HTTPException(404, "Execution not found")
    next_cursor = rows[-1]["cursor"] if rows else str(after_cursor)
    return {"events": [row for row in rows if row["event"] is not None], "next_cursor": next_cursor}


@router.get("/rest/v1/orchestrate/executions/{execution_id}/stream")
async def execution_stream(request: Request, execution_id: str,
                           after_cursor: int = Query(0, ge=0, le=MAX_SEQUENCE)):
    resume = request.headers.get("last-event-id")
    if resume is not None:
        if not re.fullmatch(r"[0-9]{1,16}", resume) or int(resume) > MAX_SEQUENCE:
            raise HTTPException(400, "Invalid Last-Event-ID")
        after_cursor = int(resume)
    if not enabled():
        raise HTTPException(404, "Execution not found")
    store = observation_store()
    if await anyio.to_thread.run_sync(lambda: store.events(execution_id, 0, 1)) is None:
        raise HTTPException(404, "Execution not found")
    close_state = await anyio.to_thread.run_sync(lambda: store.stream_close_state(execution_id, after_cursor))
    if close_state:
        state, last_cursor = close_state
        return Response(status_code=204, headers={
            "X-Execution-Stream-State": state, "X-Execution-Cursor": last_cursor,
        })

    async def stream():
        from orchestrate.server.auth import require_session_identity

        cursor = after_cursor
        last_ping = time.monotonic()
        while not await request.is_disconnected():
            try:
                await anyio.to_thread.run_sync(require_session_identity, request)
            except HTTPException:
                yield 'event: stream_error\ndata: {"code":"ACCESS_UNAVAILABLE"}\n\n'
                return
            rows = await anyio.to_thread.run_sync(lambda: store.events(execution_id, cursor, 100))
            if rows is None:
                return
            for row in rows:
                cursor = int(row["cursor"])
                yield f"id: {cursor}\ndata: {encoded(row['event'])}\n\n"
            if not rows:
                close_state = await anyio.to_thread.run_sync(lambda: store.stream_close_state(execution_id, cursor))
                if close_state:
                    state, last_cursor = close_state
                    if state == "expired":
                        yield f"event: stream_end\ndata: {encoded({'state': state, 'last_cursor': last_cursor})}\n\n"
                    return
                if time.monotonic() - last_ping >= 15:
                    yield ": keepalive\n\n"
                    last_ping = time.monotonic()
                await asyncio.sleep(.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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

"""Shared SSE execution endpoint.

The orchestration center does NOT execute workflows itself. It sends
the intent to the Workbench Agent via A2A-T, which searches/loads the
PSOP, executes the workflow, and streams SDK events back as A2A-T
TaskUpdate metadata (__sdk_event__). This module drains the stream
and forwards events to the frontend SSE.
"""

import asyncio
import json
import time
from collections import deque
from contextlib import suppress
from datetime import datetime, timezone
from typing import List

import anyio
from a2a.types import AgentCard
from fastapi.responses import StreamingResponse
from loguru import logger

from orchestrate.runtime.exec_engine import OrchestrationEngine

_EVENT_QUEUE_CAPACITY = 64
_RECORDED_EVENT_LIMIT = 1000


def _hold_stream_slot(response: StreamingResponse, semaphore: anyio.Semaphore) -> StreamingResponse:
    """Keep a dispatch slot until the response body ends or the client disconnects."""
    body_iterator = response.body_iterator

    async def limited_body():
        try:
            async for chunk in body_iterator:
                yield chunk
        finally:
            semaphore.release()

    response.body_iterator = limited_body()
    return response


async def dispatch_intent_sse(
    agent_cards: List[AgentCard],
    intent: str,
    target_agent: str = None,
    lang: str = None,
    semaphore: anyio.Semaphore | None = None,
) -> StreamingResponse:
    """Dispatch an intent to a host agent via A2A-T and stream events.

    Slim orchestration: the orchestration center does NOT execute the
    workflow itself. It sends the intent to the target host agent, which
    searches/loads the PSOP, executes it via the SDK, and streams SDK
    events back as A2A-T TaskUpdate metadata (__sdk_event__).

    This function drains the A2A-T response stream, extracts the SDK
    events from metadata, and forwards them to the frontend SSE.
    """
    if semaphore is not None:
        semaphore.acquire_nowait()

    try:
        response = _build_sse_response(agent_cards, intent, target_agent, lang)
    except BaseException:
        if semaphore is not None:
            semaphore.release()
        raise
    return _hold_stream_slot(response, semaphore) if semaphore is not None else response


def _build_sse_response(
    agent_cards: List[AgentCard], intent: str, target_agent: str | None, lang: str | None
) -> StreamingResponse:
    if not agent_cards:
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No agent cards available'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    engine = OrchestrationEngine(agent_cards, target_agent=target_agent, lang=lang)

    async def stream():
        from orchestrate.core.model.execution_record import ExecutionRecord, ExecutionStatus
        from common.custom import HandlerRegistry, InterfaceType

        started_at = datetime.now(timezone.utc)
        collected_events = deque(maxlen=_RECORDED_EVENT_LIMIT)
        dropped_events = 0
        psop_id = ""
        psop_name = ""
        final_psop = None
        record_status = ExecutionStatus.SUCCESS
        record_error = None
        saw_terminal_event = False

        HEARTBEAT_INTERVAL = 15

        event_queue = asyncio.Queue(maxsize=_EVENT_QUEUE_CAPACITY)
        done_sentinel = object()

        async def _drain_engine():
            event_stream = engine.events(intent)
            try:
                async for event in event_stream:
                    await event_queue.put(event)
            except Exception as e:
                await event_queue.put({"type": "error", "data": {"error": str(e)}, "timestamp": time.time()})
            finally:
                # Cancellation can arrive while queue.put() is backpressured, after the
                # source yielded an event. An async-for alone does not close that source.
                with suppress(Exception):
                    await event_stream.aclose()
                if not asyncio.current_task().cancelling():
                    await event_queue.put(done_sentinel)

        drain_task = asyncio.create_task(_drain_engine())

        completed_stream = False
        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=HEARTBEAT_INTERVAL)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event is done_sentinel:
                    completed_stream = True
                    break

                if len(collected_events) == _RECORDED_EVENT_LIMIT:
                    dropped_events += 1
                collected_events.append(event)
                evt_type = event.get("type", "")
                evt_data = event.get("data", {})

                if evt_type == "start":
                    wf_id = evt_data.get("workflow_id")
                    if wf_id:
                        psop_id = wf_id
                        wf_name = evt_data.get("workflow")
                        if wf_name:
                            psop_name = wf_name
                    elif not psop_name:
                        wf_name = evt_data.get("workflow")
                        if wf_name:
                            psop_name = wf_name

                elif evt_type == "psop_update":
                    psop_data = evt_data.get("psop")
                    if psop_data:
                        final_psop = psop_data
                        if not psop_id:
                            psop_id = psop_data.get("id", "")
                        if not psop_name:
                            psop_name = psop_data.get("name", "")

                elif evt_type == "error":
                    saw_terminal_event = True
                    record_status = ExecutionStatus.FAILED
                    record_error = evt_data.get("error", "Unknown error")
                elif evt_type == "cancelled":
                    saw_terminal_event = True
                    record_status = ExecutionStatus.STOPPED
                    record_error = evt_data.get("reason", "Host Agent task cancelled")
                elif evt_type == "complete":
                    saw_terminal_event = True

                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

        except Exception as e:
            record_status = ExecutionStatus.FAILED
            record_error = str(e)
            logger.error(f"[SSE] Stream error: {e}", exc_info=True)
        finally:
            if not completed_stream and record_status == ExecutionStatus.SUCCESS:
                record_status = ExecutionStatus.STOPPED
                record_error = "SSE stream closed before execution completed"
            elif completed_stream and not saw_terminal_event and record_status == ExecutionStatus.SUCCESS:
                record_status = ExecutionStatus.FAILED
                record_error = "Host Agent stream ended without a terminal workflow event"
            drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await drain_task
            if not psop_id:
                psop_id = f"dispatch-{int(time.time())}"
            if not psop_name:
                psop_name = intent[:80]

            try:
                record = ExecutionRecord(
                    psop_id=psop_id,
                    psop_name=psop_name,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    status=record_status,
                    execution_history=[],
                    final_psop=final_psop,
                    events=([{"type": "events_truncated", "data": {"dropped": dropped_events}}]
                            if dropped_events else []) + list(collected_events),
                    error=record_error,
                )
                handler = HandlerRegistry.get_handler(InterfaceType.SAVE_EXECUTION_RECORD)
                handler.handle(record)
                logger.info(f"[SSE] Execution record saved: {record.execution_id} (status={record_status.value})")
            except Exception as e:
                logger.error(f"[SSE] Failed to save execution record: {e}", exc_info=True)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

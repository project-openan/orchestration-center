# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for sse_executor.dispatch_intent_sse.

Drives the async generator with a stub OrchestrationEngine, exercising:
- empty agent_cards -> error stream
- normal event flow (start, psop_update, generic)
- error event -> ExecutionStatus.FAILED
- engine exception -> error event in queue
- heartbeat timeout -> ': heartbeat' comment
- ExecutionRecord save in finally block
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anyio
from starlette.responses import StreamingResponse

from orchestrate.server.sse_executor import dispatch_intent_sse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubEngine:
    """Minimal async iterator that yields pre-defined events."""

    def __init__(self, events=None, exc=None):
        self._events = events or []
        self._exc = exc

    async def events(self, intent):
        for evt in self._events:
            yield evt
        if self._exc:
            raise self._exc


def _collect_stream(response: StreamingResponse):
    """Drain a StreamingResponse's body iterator synchronously."""
    import asyncio as _aio

    async def _drain():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    loop = _aio.new_event_loop()
    try:
        return loop.run_until_complete(_drain())
    finally:
        loop.close()


def _run_and_collect(coro):
    """Run an async coroutine and return the result."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================================================
# 1. Empty agent_cards -> error stream
# ===========================================================================

class TestEmptyAgentCards:
    def test_error_stream_returned(self):
        response = _run_and_collect(dispatch_intent_sse([], "test intent"))
        assert isinstance(response, StreamingResponse)
        chunks = _collect_stream(response)
        assert len(chunks) == 1
        data = json.loads(chunks[0].removeprefix("data: ").strip())
        assert data["type"] == "error"
        assert "No agent cards" in data["message"]


@pytest.mark.asyncio
async def test_dispatch_slot_is_held_until_stream_is_consumed():
    semaphore = anyio.Semaphore(1)
    first = await dispatch_intent_sse([], "first", semaphore=semaphore)
    with pytest.raises(anyio.WouldBlock):
        await dispatch_intent_sse([], "second", semaphore=semaphore)
    assert [chunk async for chunk in first.body_iterator]
    second = await dispatch_intent_sse([], "second", semaphore=semaphore)
    assert [chunk async for chunk in second.body_iterator]


@pytest.mark.asyncio
async def test_incomplete_stream_is_not_recorded_as_success():
    from orchestrate.core.model.execution_record import ExecutionStatus

    with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine([{"type": "start", "data": {}}])):
        with patch("common.custom.HandlerRegistry") as registry, \
             patch("orchestrate.core.model.execution_record.ExecutionRecord") as record:
            registry.get_handler.return_value = MagicMock()
            record.return_value = MagicMock(execution_id="record-1")
            response = await dispatch_intent_sse([MagicMock()], "intent")
            assert [chunk async for chunk in response.body_iterator]
            assert record.call_args.kwargs["status"] == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_recorded_events_are_bounded_and_note_truncation():
    events = [{"type": "progress", "data": {"index": index}} for index in range(5)]
    events.append({"type": "complete", "data": {}})
    with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)), \
         patch("orchestrate.server.sse_executor._RECORDED_EVENT_LIMIT", 3), \
         patch("common.custom.HandlerRegistry") as registry, \
         patch("orchestrate.core.model.execution_record.ExecutionRecord") as record:
        registry.get_handler.return_value = MagicMock()
        record.return_value = MagicMock(execution_id="record-2")
        response = await dispatch_intent_sse([MagicMock()], "intent")
        assert len([chunk async for chunk in response.body_iterator]) == 6
        saved_events = record.call_args.kwargs["events"]
        assert saved_events[0] == {"type": "events_truncated", "data": {"dropped": 3}}
        assert saved_events[-1]["type"] == "complete"


@pytest.mark.asyncio
async def test_disconnecting_backpressured_stream_closes_engine_and_records_stop():
    from orchestrate.core.model.execution_record import ExecutionStatus

    source_closed = asyncio.Event()
    produced = 0

    class EndlessEngine:
        async def events(self, intent):
            nonlocal produced
            try:
                while True:
                    produced += 1
                    yield {"type": "progress", "data": {"index": produced}}
            finally:
                source_closed.set()

    with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=EndlessEngine()), \
         patch("common.custom.HandlerRegistry") as registry, \
         patch("orchestrate.core.model.execution_record.ExecutionRecord") as record:
        registry.get_handler.return_value = MagicMock()
        record.return_value = MagicMock(execution_id="record-disconnected")
        response = await dispatch_intent_sse([MagicMock()], "intent")
        await anext(response.body_iterator)
        await asyncio.sleep(0.01)
        assert produced <= 66, "a slow consumer must backpressure the engine"

        await response.body_iterator.aclose()

        assert source_closed.is_set()
        assert record.call_args.kwargs["status"] == ExecutionStatus.STOPPED


# ===========================================================================
# 2. Normal event flow
# ===========================================================================

class TestNormalFlow:
    def test_start_and_generic_event(self):
        events = [
            {"type": "start", "data": {"workflow_id": "wf-1", "workflow": "MyWF"}},
            {"type": "progress", "data": {"step": 1}},
        ]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_reg.get_handler.return_value = MagicMock()
                mock_er.return_value = MagicMock(execution_id="test-1")
                response = _run_and_collect(dispatch_intent_sse([MagicMock(name="agent1")], "test"))
                chunks = _collect_stream(response)
                # 2 data events
                data_chunks = [c for c in chunks if c.startswith("data: ")]
                assert len(data_chunks) == 2
                first = json.loads(data_chunks[0].removeprefix("data: ").strip())
                assert first["type"] == "start"
                assert first["data"]["workflow_id"] == "wf-1"

    def test_psop_update_event(self):
        events = [
            {"type": "psop_update", "data": {"psop": {"id": "psop-1", "name": "Test"}}},
        ]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_reg.get_handler.return_value = MagicMock()
                mock_er.return_value = MagicMock(execution_id="test-2")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "intent"))
                chunks = _collect_stream(response)
                data_chunks = [c for c in chunks if c.startswith("data: ")]
                assert len(data_chunks) == 1
                evt = json.loads(data_chunks[0].removeprefix("data: ").strip())
                assert evt["type"] == "psop_update"


# ===========================================================================
# 3. Error event from engine
# ===========================================================================

class TestErrorEvent:
    def test_error_event_sets_failed_status(self):
        events = [
            {"type": "error", "data": {"error": "Something went wrong"}},
        ]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_handler = MagicMock()
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="test-3")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "intent"))
                chunks = _collect_stream(response)
                data_chunks = [c for c in chunks if c.startswith("data: ")]
                assert len(data_chunks) == 1
                evt = json.loads(data_chunks[0].removeprefix("data: ").strip())
                assert evt["type"] == "error"
                # ExecutionRecord was saved
                mock_handler.handle.assert_called_once()


# ===========================================================================
# 4. Engine raises exception -> error event queued
# ===========================================================================

class TestEngineException:
    def test_engine_exception_produces_error_event(self):
        events = []
        with patch("orchestrate.server.sse_executor.OrchestrationEngine",
                   return_value=_StubEngine(events, exc=RuntimeError("engine crash"))):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_handler = MagicMock()
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="test-4")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "intent"))
                chunks = _collect_stream(response)
                data_chunks = [c for c in chunks if c.startswith("data: ")]
                # The exception is caught in _drain_engine and an error event is queued
                assert len(data_chunks) == 1
                evt = json.loads(data_chunks[0].removeprefix("data: ").strip())
                assert evt["type"] == "error"
                assert "engine crash" in evt["data"]["error"]


# ===========================================================================
# 5. Heartbeat timeout
# ===========================================================================

class TestHeartbeat:
    def test_heartbeat_on_timeout(self):
        """When the engine yields no events for HEARTBEAT_INTERVAL seconds,
        a ': heartbeat\\n\\n' comment should be yielded."""
        events = [{"type": "done", "data": {}}]

        call_count = 0

        async def fast_wait_for(coro, timeout):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First two calls: simulate timeout
                coro.close()  # suppress unused coroutine warning
                raise asyncio.TimeoutError()
            return await coro

        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er, \
                 patch("asyncio.wait_for", side_effect=fast_wait_for):
                mock_handler = MagicMock()
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="test-5")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "intent"))
                chunks = _collect_stream(response)
                # Should contain heartbeat comments
                heartbeat_chunks = [c for c in chunks if c.startswith(": heartbeat")]
                assert len(heartbeat_chunks) == 2
                # Should also contain the real event
                data_chunks = [c for c in chunks if c.startswith("data: ")]
                assert len(data_chunks) == 1


# ===========================================================================
# 6. ExecutionRecord saved in finally block
# ===========================================================================

class TestExecutionRecordSave:
    def test_record_saved_on_success(self):
        events = [{"type": "start", "data": {"workflow_id": "wf-final"}}]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_handler = MagicMock()
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="rec-1")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "my intent"))
                _collect_stream(response)
                # handle() should have been called with the record
                mock_handler.handle.assert_called_once()
                # ExecutionRecord was constructed with correct psop_id
                call_args = mock_er.call_args
                assert call_args.kwargs["psop_id"] == "wf-final"

    def test_record_saved_with_dispatch_id_when_no_psop_id(self):
        events = [{"type": "progress", "data": {}}]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                mock_handler = MagicMock()
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="rec-2")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "fallback intent"))
                _collect_stream(response)
                mock_handler.handle.assert_called_once()
                call_args = mock_er.call_args
                # psop_id should start with "dispatch-"
                assert call_args.kwargs["psop_id"].startswith("dispatch-")
                # psop_name should be the intent
                assert call_args.kwargs["psop_name"] == "fallback intent"

    def test_record_save_failure_does_not_crash(self):
        events = [{"type": "start", "data": {"workflow_id": "wf-err"}}]
        with patch("orchestrate.server.sse_executor.OrchestrationEngine", return_value=_StubEngine(events)):
            with patch("common.custom.HandlerRegistry") as mock_reg, \
                 patch("orchestrate.core.model.execution_record.ExecutionRecord") as mock_er:
                # handle() raises -- the finally block should swallow this
                mock_handler = MagicMock()
                mock_handler.handle.side_effect = RuntimeError("db unavailable")
                mock_reg.get_handler.return_value = mock_handler
                mock_er.return_value = MagicMock(execution_id="rec-3")
                response = _run_and_collect(dispatch_intent_sse([MagicMock()], "intent"))
                # Should not raise
                chunks = _collect_stream(response)
                assert len(chunks) > 0

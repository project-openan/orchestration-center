# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""A caller-selected PSOP must survive the entire center -> Host relay."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from workflow_engine import A2AStreamEvent

from host_agent.runtime import HostAgentExecutor
from orchestrate.core.model.psop import PSOP, TaskStatus
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.runtime.exec_engine import OrchestrationEngine
from orchestrate.server import external_api, frontend_support_server, sse_executor


@pytest.fixture
def relay(monkeypatch, sample_psop_dict):
    selected = PSOP.model_validate({**sample_psop_dict, "id": "requested-A"})
    other = selected.model_copy(deep=True)
    other.id = "search-result-B"
    other.steps[0].subtasks[0].description = "Do something else (B)"
    retrieval = MagicMock()
    retrieval.get_psop_by_id.side_effect = lambda identifier: {
        selected.id: selected, other.id: other,
    }.get(identifier)
    retrieval.retrieve_psop_by_intent_topn.return_value = [
        SimpleNamespace(workflow_id=other.id, name=other.name)
    ]
    sent, records = [], []

    class Client:
        closed = False

        async def stream_message(self, agent_name, content):
            sent.append((agent_name, content))
            yield A2AStreamEvent(
                event_type="status_update", task_id="task-1", context_id="ctx-1",
                task_state="TASK_STATE_WORKING",
                metadata={"__sdk_event__": json.dumps({
                    "type": "task_status_changed",
                    "data": {"step": "step1", "subtask_index": 0, "status": "success"},
                })},
            )
            yield A2AStreamEvent(
                event_type="status_update", task_id="task-1", context_id="ctx-1",
                task_state="TASK_STATE_COMPLETED", metadata={},
            )

        async def close(self):
            self.closed = True

    client = Client()
    cards = AsyncMock(return_value=[SimpleNamespace(name="Host Agent")])
    storage = SimpleNamespace(handle=records.append)
    monkeypatch.setattr(SharedHandlers, "retrieval", lambda: retrieval)
    monkeypatch.setattr(external_api, "get_agent_cards", cards)
    monkeypatch.setattr(frontend_support_server, "get_agent_cards", cards)
    monkeypatch.setattr(OrchestrationEngine, "_get_engine_client", lambda self: client)
    monkeypatch.setattr("common.util.config_util.get_conf", lambda: {})
    monkeypatch.delenv("ORCH_AGENT_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler", lambda *args: storage)
    return SimpleNamespace(selected=selected, other=other, retrieval=retrieval,
                           sent=sent, records=records, client=client)


async def collect(response):
    frames = [frame async for frame in response.body_iterator]
    return [json.loads(frame.removeprefix("data: ")) for frame in frames if frame.startswith("data: ")]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["internal", "external"])
async def test_execute_by_id_keeps_requested_snapshot_and_record(relay, endpoint):
    original = relay.selected.model_dump(mode="json")
    if endpoint == "internal":
        response = await frontend_support_server.execute_workflow(
            request=MagicMock(),
            psop_id=relay.selected.id, user_intent="shared purpose",
            target_agent="Host Agent", lang="en",
            scope=None, authorized_instances=None, caller_id=None,
            task_overrides=None, group_overrides=None, tie_break=None,
        )
    else:
        response = await external_api.execute_psop_by_id(
            MagicMock(), relay.selected.id, user_intent="shared purpose", lang="en",
            scope=None, authorized_instances=None, caller_id=None,
            task_overrides=None, group_overrides=None, tie_break=None,
        )
    events = await collect(response)
    assert len(relay.sent) == 1
    target, content = relay.sent[0]
    assert target == "Host Agent"
    assert content.parts[0].text == "shared purpose"
    assert content.metadata["__orch_psop_id__"] == "requested-A"
    assert json.loads(content.metadata["__orch_psop__"]) == original
    relay.retrieval.retrieve_psop_by_intent_topn.assert_not_called()
    assert relay.selected.model_dump(mode="json") == original
    assert relay.records[0].psop_id == "requested-A"
    assert relay.records[0].final_psop["id"] == "requested-A"
    assert relay.records[0].status.value == "success"
    assert {event["data"]["psop"]["id"] for event in events if event["type"] == "psop_update"} == {"requested-A"}
    assert events[-1]["type"] == "complete"
    assert relay.client.closed


@pytest.mark.asyncio
async def test_bound_snapshot_is_captured_before_stream_consumption(relay):
    original = relay.selected.model_dump(mode="json")
    response = await sse_executor.dispatch_intent_sse(
        [SimpleNamespace(name="Host Agent")], "shared purpose", psop=relay.selected,
    )
    relay.selected.name = "edited after dispatch"
    relay.selected.steps[0].subtasks[0].description = "edited after dispatch"
    await collect(response)
    assert json.loads(relay.sent[0][1].metadata["__orch_psop__"]) == original


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["auto", "dispatch"])
async def test_intent_only_keeps_search_behavior_and_does_not_mutate_store(relay, endpoint):
    if endpoint == "auto":
        response = await external_api.execute_workflow(
            MagicMock(), external_api.ExecuteRequest(task="shared purpose"), lang="en",
        )
    else:
        response = await frontend_support_server.dispatch_to_agent(
            intent="shared purpose", agent_name="Host Agent", lang="en",
        )
    await collect(response)
    if endpoint == "auto":
        relay.retrieval.retrieve_psop_by_intent_topn.assert_called_once_with("shared purpose", 3)
        assert relay.sent[0][1].metadata["__orch_psop_id__"] == "search-result-B"
    else:
        relay.retrieval.retrieve_psop_by_intent_topn.assert_not_called()
        assert not relay.sent[0][1].metadata
    assert relay.other.steps[0].subtasks[0].status == TaskStatus.PENDING


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["internal", "external"])
async def test_missing_requested_workflow_is_404_without_fallback(relay, endpoint):
    with pytest.raises(HTTPException) as error:
        if endpoint == "internal":
            await frontend_support_server.execute_workflow(
                request=MagicMock(),
                psop_id="missing", user_intent="shared purpose", target_agent=None, lang="en",
            )
        else:
            await external_api.execute_psop_by_id(
                MagicMock(), "missing", user_intent="shared purpose", lang="en",
            )
    assert error.value.status_code == 404
    relay.retrieval.retrieve_psop_by_intent_topn.assert_not_called()
    assert not relay.sent


@pytest.mark.asyncio
async def test_intent_without_match_fails_without_dispatch(relay):
    relay.retrieval.retrieve_psop_by_intent_topn.return_value = []
    response = await sse_executor.dispatch_intent_sse(
        [SimpleNamespace(name="Host Agent")], "new intent",
    )
    events = await collect(response)
    assert not relay.sent
    assert events[-1]["data"]["code"] == "PSOP_NOT_FOUND"
    assert relay.records[0].status.value == "failed"


@pytest.mark.asyncio
async def test_intent_without_match_returns_real_host_failure(relay, monkeypatch):
    """Raw dispatch is not generation: the actual default Host must report failure."""
    from a2a.types import TaskState
    from host_agent.config import HostAgentConfig
    from host_agent.execution import HostExecutionTracker
    from host_agent.workflow_repository import OrchestrationWorkflowRepository

    search = AsyncMock(return_value=[])
    monkeypatch.setattr("host_agent.workflow_repository.search_psop", search)
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._execution_tracker = HostExecutionTracker()
    executor._config = HostAgentConfig(orchestration_url="https://orch.test", registry_url="https://registry.test")
    executor._workflow_repository = OrchestrationWorkflowRepository(orch_url="https://orch.test")
    executor._load_agent_cards = AsyncMock()
    relay.retrieval.retrieve_psop_by_intent_topn.return_value = []

    class HostBridge:
        async def stream_message(self, agent_name, content):
            updates = []

            async def enqueue(event):
                updates.append(event)

            context = SimpleNamespace(task_id="no-match-task", context_id="no-match-context",
                                      metadata=dict(content.metadata), message=None,
                                      get_user_input=lambda: content.parts[0].text)
            await executor.execute(context, SimpleNamespace(enqueue_event=enqueue))
            for update in updates:
                yield A2AStreamEvent(event_type="status_update", task_id=context.task_id,
                                     context_id=context.context_id,
                                     task_state=TaskState.Name(update.status.state), metadata=dict(update.metadata))

        async def close(self):
            pass

    monkeypatch.setattr(OrchestrationEngine, "_get_engine_client", lambda self: HostBridge())
    response = await external_api.execute_workflow(
        MagicMock(), external_api.ExecuteRequest(task="new intent"), lang="en",
    )
    events = await collect(response)
    assert response.status_code == 200
    assert events[-1]["type"] == "error"
    assert "No matching workflow found" in events[-1]["data"]["error"]
    assert not any(event["type"] == "complete" for event in events)
    assert relay.records[0].status.value == "failed"
    search.assert_not_awaited()
    executor._load_agent_cards.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", [None, "", " ", 42])
async def test_host_rejects_explicit_empty_id_without_fallback(identifier):
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._workflow_repository = SimpleNamespace(get=AsyncMock(), find=AsyncMock())
    context = SimpleNamespace(message=None, metadata={"__orch_psop_id__": identifier})
    with pytest.raises(ValueError, match="ID"):
        await executor._resolve_workflow(context, "shared purpose")
    executor._workflow_repository.get.assert_not_awaited()
    executor._workflow_repository.find.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", [None, {}, "", "not-json", [], {"id": "B", "steps": []},
                                          {"steps": []}, {"id": "A", "steps": "invalid"}])
async def test_host_rejects_invalid_explicit_snapshot_without_fallback(snapshot):
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._workflow_repository = SimpleNamespace(get=AsyncMock(), find=AsyncMock())
    context = SimpleNamespace(message=None, metadata={"__orch_psop_id__": "A", "__orch_psop__": snapshot})
    with pytest.raises(ValueError):
        await executor._resolve_workflow(context, "shared purpose")
    executor._workflow_repository.get.assert_not_awaited()
    executor._workflow_repository.find.assert_not_awaited()


@pytest.mark.asyncio
async def test_host_rejects_id_only_repository_mismatch_without_intent_fallback():
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._workflow_repository = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id="B")), find=AsyncMock(),
    )
    context = SimpleNamespace(message=None, metadata={"__orch_psop_id__": "A"})
    with pytest.raises(ValueError, match="ID"):
        await executor._resolve_workflow(context, "shared purpose")
    executor._workflow_repository.find.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("encoded", [False, True])
async def test_host_uses_matching_snapshot_without_repository(relay, encoded):
    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._workflow_repository = SimpleNamespace(get=AsyncMock(), find=AsyncMock())
    snapshot = relay.selected.model_dump(mode="json")
    context = SimpleNamespace(message=None, metadata={
        "__orch_psop_id__": "requested-A",
        "__orch_psop__": json.dumps(snapshot) if encoded else snapshot,
    })
    resolved = await executor._resolve_workflow(context, "shared purpose")
    assert resolved["id"] == "requested-A"
    executor._workflow_repository.get.assert_not_awaited()
    executor._workflow_repository.find.assert_not_awaited()


@pytest.mark.parametrize("transport", ["http", "https"])
@pytest.mark.parametrize("endpoint", ["internal", "external"])
def test_requested_workflow_runs_in_host_over_real_http_transport(
    relay, monkeypatch, tmp_path, transport, endpoint,
):
    """Real center socket and real Host/SDK execution; A2A/worker I/O is injected."""
    import hashlib
    import socket
    import ssl
    import threading
    import time

    import httpx
    import uvicorn
    from workflow_engine import MessageContent, StubWorkflowEngineClient
    from a2a.types import TaskState
    from host_agent.config import HostAgentConfig
    from host_agent.execution import HostExecutionTracker
    from orchestrate.server import auth, account_api, middleware
    from test_storage_http_transport import _tls_files

    conf = {"persistence_mode": "file", "enable_https": str(transport == "https").lower(),
            "verify_client": "false", "external.auth.mode": "user",
            "access_password": hashlib.sha256(b"SyntheticBinding9!").hexdigest()}
    storage = SimpleNamespace(has_users=False)
    monkeypatch.setattr(auth, "get_conf", lambda: conf)
    monkeypatch.setattr(auth, "current_context", lambda: storage)
    monkeypatch.setattr(account_api, "current_context", lambda: storage)
    monkeypatch.setattr(auth, "_session_store", auth._SessionStore())
    monkeypatch.setattr(auth, "_pending_password_change", set())
    monkeypatch.setattr(middleware, "limiter", middleware.strategies.MovingWindowRateLimiter(middleware.storage.MemoryStorage()))
    monkeypatch.setattr(frontend_support_server, "is_auth_enabled", lambda: True)

    executed = []

    class ControlPoint:
        def __init__(self, context):
            pass

        async def on_task(self, request):
            executed.append(request.instruction)
            return MessageContent.text(request.instruction)

    executor = HostAgentExecutor.__new__(HostAgentExecutor)
    executor._execution_tracker = HostExecutionTracker()
    executor._config = HostAgentConfig(orchestration_url="http://unused.test", registry_url="http://unused.test")
    executor._extension_lifecycle = None
    executor._workflow_repository = SimpleNamespace(get=AsyncMock(), find=AsyncMock())
    executor._load_agent_cards = AsyncMock(return_value=[SimpleNamespace(name="agent_a")])
    executor._engine_client_factory = SimpleNamespace(create=lambda cards: StubWorkflowEngineClient())
    executor._control_point_factory = ControlPoint

    class HostBridge:
        async def stream_message(self, agent_name, content):
            relay.sent.append((agent_name, content))
            updates = []

            class Queue:
                async def enqueue_event(self, event):
                    updates.append(event)

            context = SimpleNamespace(task_id="http-task", context_id="http-context",
                                      metadata=dict(content.metadata), message=None,
                                      get_user_input=lambda: content.parts[0].text)
            await executor.execute(context, Queue())
            for update in updates:
                yield A2AStreamEvent(
                    event_type="status_update", task_id="http-task", context_id="http-context",
                    task_state=TaskState.Name(update.status.state), metadata=dict(update.metadata),
                )

        async def close(self):
            pass

    monkeypatch.setattr(OrchestrationEngine, "_get_engine_client", lambda self: HostBridge())
    # Fresh loop-owned semaphores; do not reuse those bound by another test loop.
    import anyio
    monkeypatch.setattr(frontend_support_server, "execute_semaphore", anyio.Semaphore(1))
    monkeypatch.setattr(external_api, "execute_semaphore", anyio.Semaphore(1))
    options, verify = {}, True
    if transport == "https":
        cert, key = _tls_files(tmp_path)
        options = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        verify = ssl.create_default_context(cafile=str(cert))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    base = f"{transport}://127.0.0.1:{listener.getsockname()[1]}"
    runner = uvicorn.Server(uvicorn.Config(frontend_support_server.app, lifespan="off", log_level="error", **options))
    thread = threading.Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not runner.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started
        if endpoint == "internal":
            path, params = "/rest/v1/orchestrate/execute", {"psop_id": "requested-A", "user_intent": "shared purpose"}
        else:
            path, params = "/api/v1/orchestrate/execute/requested-A", {"user_intent": "shared purpose"}
        with httpx.Client(base_url=base, verify=verify, trust_env=False, timeout=10) as client:
            assert client.get(path, params=params).status_code == 401
            issued = client.post("/api/v1/auth/token", json={"username": "admin", "password": "SyntheticBinding9!"})
            assert issued.status_code == 200, issued.text
            response = client.get(path, params=params, headers={"Authorization": "Bearer " + issued.json()["access_token"]})
            assert response.status_code == 200, response.text
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert any(event["type"] == "complete" for event in events), events
            assert not any(event["type"] == "error" for event in events), events
        assert executed == ["Do something"]
        assert relay.sent[0][1].metadata["__orch_psop_id__"] == "requested-A"
        relay.retrieval.retrieve_psop_by_intent_topn.assert_not_called()
        executor._workflow_repository.get.assert_not_awaited()
        executor._workflow_repository.find.assert_not_awaited()
        assert relay.records[0].psop_id == "requested-A"
        assert relay.records[0].status.value == "success"
    finally:
        runner.should_exit = True
        thread.join(10)
        listener.close()
        assert not thread.is_alive()

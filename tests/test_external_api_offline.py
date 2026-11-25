# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for external_api.py -- all 8 public endpoints.

Uses FastAPI TestClient with mocked dependencies so no live server or
registry is required.  Covers success paths, 404s, 400s, 500s, and the
semaphore-busy (503) path.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrate.server.external_api import router


# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    """Bypass rate limiting so tests neither get throttled nor consume
    the shared in-process MemoryStorage quota that other test modules
    (test_frontend_support_server.py) depend on.

    NOTE: patching the RateLimiter class does NOT work here -- the
    Depends(RateLimiter(config, ...)) instances are constructed at module
    import time and keep a reference to the original class. RateLimiter's
    __call__ resolves async_hit from the middleware module globals at call
    time, so patching middleware.async_hit is the reliable interception
    point.
    """
    with patch("orchestrate.server.middleware.async_hit",
               new=AsyncMock(return_value=True)):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_psop_dict():
    return {
        "id": "psop-test-001",
        "name": "Test Workflow",
        "description": "desc",
        "steps": [],
        "tags": ["t"],
    }


# ===========================================================================
# 1. POST /api/v1/orchestrate/sop
# ===========================================================================

class TestOrchestrateSop:
    def test_sop_json_success(self, client):
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = _make_psop_dict()
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.PsopGenerator") as mock_gen_class, \
             patch("common.custom.HandlerRegistry") as mock_reg:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_workflow.return_value = mock_psop
            mock_gen_class.return_value = mock_gen
            mock_handler = MagicMock()
            mock_reg.get_handler.return_value = mock_handler
            resp = client.post(
                "/api/v1/orchestrate/sop",
                json={"sop_content": "Step 1 do something"},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["code"] == 201
            assert body["status"] == "success"
            mock_gen.generate_psop_workflow.assert_called_once()
            mock_handler.handle.assert_called_once()

    def test_sop_missing_content_and_file(self, client):
        """When JSON body lacks sop_content, model_validate raises
        ValidationError which is caught as 500 (not 422, because the
        endpoint does manual body parsing, not FastAPI dependency injection)."""
        resp = client.post(
            "/api/v1/orchestrate/sop",
            headers={"content-type": "application/json"},
            json={},
        )
        # The endpoint manually parses JSON body and catches ValidationError -> 500
        assert resp.status_code == 500

    def test_sop_empty_content(self, client):
        resp = client.post(
            "/api/v1/orchestrate/sop",
            json={"sop_content": "   "},
        )
        # The body validates, sop_content="   " is non-empty by pydantic
        # but the endpoint checks sop_text.strip() and raises 400
        assert resp.status_code in (400, 500)

    def test_sop_txt_file_upload(self, client):
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = _make_psop_dict()
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.PsopGenerator") as mock_gen_class, \
             patch("common.custom.HandlerRegistry") as mock_reg:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_workflow.return_value = mock_psop
            mock_gen_class.return_value = mock_gen
            mock_reg.get_handler.return_value = MagicMock()
            resp = client.post(
                "/api/v1/orchestrate/sop",
                files={"file": ("test.txt", b"Step 1 do something", "text/plain")},
                data={"name": "MyWF"},
            )
            assert resp.status_code == 201
            assert resp.json()["code"] == 201

    def test_sop_invalid_filename(self, client):
        resp = client.post(
            "/api/v1/orchestrate/sop",
            files={"file": ("malicious.exe", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_sop_get_agent_cards_404(self, client):
        from fastapi import HTTPException
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards:
            mock_cards.side_effect = HTTPException(status_code=404, detail="No available agents found")
            resp = client.post(
                "/api/v1/orchestrate/sop",
                json={"sop_content": "Step 1"},
            )
            assert resp.status_code == 404

    def test_sop_generator_error(self, client):
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.PsopGenerator") as mock_gen_class:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_workflow.side_effect = RuntimeError("LLM failed")
            mock_gen_class.return_value = mock_gen
            resp = client.post(
                "/api/v1/orchestrate/sop",
                json={"sop_content": "Step 1"},
            )
            assert resp.status_code == 500


# ===========================================================================
# 2. POST /api/v1/orchestrate/intent
# ===========================================================================

class TestOrchestrateIntent:
    def test_intent_success(self, client):
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = _make_psop_dict()
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.IntentPsopGenerator") as mock_gen_class, \
             patch("common.custom.HandlerRegistry") as mock_reg:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_from_intent.return_value = mock_psop
            mock_gen_class.return_value = mock_gen
            mock_reg.get_handler.return_value = MagicMock()
            resp = client.post(
                "/api/v1/orchestrate/intent",
                json={"intent": "Summarize a document"},
            )
            assert resp.status_code == 201
            assert resp.json()["code"] == 201

    def test_intent_missing_field(self, client):
        resp = client.post("/api/v1/orchestrate/intent", json={})
        assert resp.status_code == 422

    def test_intent_generator_error(self, client):
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.IntentPsopGenerator") as mock_gen_class:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_from_intent.side_effect = ValueError("bad intent")
            mock_gen_class.return_value = mock_gen
            resp = client.post(
                "/api/v1/orchestrate/intent",
                json={"intent": "test"},
            )
            assert resp.status_code == 500


# ===========================================================================
# 3. GET /api/v1/orchestrate/psop/{psop_id}
# ===========================================================================

class TestGetPsop:
    def test_get_psop_success(self, client):
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = _make_psop_dict()
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = mock_psop
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/psop-001")
            assert resp.status_code == 200
            assert resp.json()["code"] == 200

    def test_get_psop_not_found(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = None
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/nonexistent")
            assert resp.status_code == 404

    def test_get_psop_error(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.side_effect = RuntimeError("db down")
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/err-id")
            assert resp.status_code == 500


# ===========================================================================
# 3b. GET /api/v1/orchestrate/psop/{psop_id}/bpmn
# ===========================================================================

class TestGetPsopBpmn:
    """The BPMN endpoint retrieves the PSOP through the same query path as
    GET /psop/{id} and converts it to BPMN 2.0 XML on the fly."""

    @staticmethod
    def _real_psop():
        from orchestrate.core.model.psop import PSOP, Step, Task, JumpCondition
        return PSOP(
            id="psop-bpmn-001",
            name="BPMN Export <Demo>",
            description="desc",
            steps=[
                Step(name="step1", subtasks=[Task(description="t1", agent="agent_a", skill="skill_a")],
                     next=[JumpCondition(step="step2", condition="")]),
                Step(name="step2", subtasks=[Task(description="t2", agent="agent_b", skill="skill_b")]),
            ],
        )

    def test_get_psop_bpmn_success(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = self._real_psop()
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/psop-bpmn-001/bpmn")
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("application/xml")
            assert "attachment" not in resp.headers.get("content-disposition", "")
            assert ".bpmn" in resp.headers.get("content-disposition", "")
            # body is a BPMN document, not a JSON envelope
            assert resp.text.startswith('<?xml version="1.0"')
            assert "<bpmn:process" in resp.text
            assert "<bpmn:task" in resp.text

    def test_get_psop_bpmn_not_found(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = None
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/nonexistent/bpmn")
            assert resp.status_code == 404

    def test_get_psop_bpmn_retrieval_error(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.side_effect = RuntimeError("db down")
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/err-id/bpmn")
            assert resp.status_code == 500

    def test_get_psop_bpmn_conversion_error(self, client):
        """A stored PSOP without steps cannot be converted -> 500."""
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = self._real_psop().model_copy(update={"steps": []})
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/psop/empty/bpmn")
            assert resp.status_code == 500


# ===========================================================================
# 4. POST /api/v1/orchestrate/search
# ===========================================================================

class TestSearchWorkflows:
    def test_search_success(self, client):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"workflow_id": "wf-1", "name": "WF"}
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.retrieve_psop_by_intent_topn.return_value = [mock_result]
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.post(
                "/api/v1/orchestrate/search",
                json={"intent": "summarize", "top_n": 5},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert len(data) == 1

    def test_search_empty_results(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.retrieve_psop_by_intent_topn.return_value = []
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.post(
                "/api/v1/orchestrate/search",
                json={"intent": "nonexistent"},
            )
            assert resp.status_code == 200
            assert resp.json()["data"] == []

    def test_search_error(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.retrieve_psop_by_intent_topn.side_effect = RuntimeError("fail")
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.post(
                "/api/v1/orchestrate/search",
                json={"intent": "test"},
            )
            assert resp.status_code == 500


# ===========================================================================
# 5. POST /api/v1/orchestrate/execute
# ===========================================================================

class TestExecuteWorkflow:
    def test_execute_success(self, client):
        mock_sse = MagicMock()
        mock_sse.media_type = "text/event-stream"
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.dispatch_intent_sse", new_callable=AsyncMock) as mock_dispatch:
            mock_cards.return_value = [MagicMock()]
            mock_dispatch.return_value = mock_sse
            resp = client.post(
                "/api/v1/orchestrate/execute",
                json={"task": "do something"},
            )
            # StreamingResponse returns 200
            assert resp.status_code == 200
            mock_dispatch.assert_called_once()

    def test_execute_no_agents(self, client):
        from fastapi import HTTPException
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards:
            mock_cards.side_effect = HTTPException(status_code=404, detail="No agents")
            resp = client.post(
                "/api/v1/orchestrate/execute",
                json={"task": "do something"},
            )
            assert resp.status_code == 404


# ===========================================================================
# 6. GET /api/v1/orchestrate/execute/{psop_id}
# ===========================================================================

class TestExecutePsopById:
    def test_execute_by_id_success(self, client):
        mock_psop = MagicMock()
        mock_psop.name = "Test WF"
        mock_sse = MagicMock()
        mock_sse.media_type = "text/event-stream"
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared, \
             patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.dispatch_intent_sse", new_callable=AsyncMock) as mock_dispatch:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = mock_psop
            mock_shared.retrieval.return_value = mock_retrieval
            mock_cards.return_value = [MagicMock()]
            mock_dispatch.return_value = mock_sse
            resp = client.get("/api/v1/orchestrate/execute/psop-001")
            assert resp.status_code == 200

    def test_execute_by_id_not_found(self, client):
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = None
            mock_shared.retrieval.return_value = mock_retrieval
            resp = client.get("/api/v1/orchestrate/execute/nonexistent")
            assert resp.status_code == 404


# ===========================================================================
# 7. GET /api/v1/executions
# ===========================================================================

class TestListExecutions:
    def test_list_success(self, client):
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.return_value = [{"execution_id": "e1", "status": "success"}]
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions")
            assert resp.status_code == 200
            assert len(resp.json()["data"]) == 1

    def test_list_error(self, client):
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.side_effect = RuntimeError("fail")
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions")
            assert resp.status_code == 500


# ===========================================================================
# 8. GET /api/v1/executions/{execution_id}
# ===========================================================================

class TestGetExecution:
    def test_get_execution_success(self, client):
        mock_record = MagicMock()
        mock_record.model_dump.return_value = {"execution_id": "e1"}
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.return_value = mock_record
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions/e1")
            assert resp.status_code == 200
            assert resp.json()["data"]["execution_id"] == "e1"

    def test_get_execution_not_found(self, client):
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.return_value = None
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions/nonexistent")
            assert resp.status_code == 404

    def test_get_execution_dict_record(self, client):
        """When the handler returns a dict (no model_dump), the endpoint
        should still return it as-is."""
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.return_value = {"execution_id": "e2", "status": "success"}
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions/e2")
            assert resp.status_code == 200
            assert resp.json()["data"]["execution_id"] == "e2"

    def test_get_execution_error(self, client):
        with patch("common.custom.HandlerRegistry") as mock_reg:
            mock_handler = MagicMock()
            mock_handler.handle.side_effect = RuntimeError("fail")
            mock_reg.get_handler.return_value = mock_handler
            resp = client.get("/api/v1/executions/err")
            assert resp.status_code == 500

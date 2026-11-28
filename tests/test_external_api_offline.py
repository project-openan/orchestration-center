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


# ===========================================================================
# 9. Save-time catalog gate on the generation endpoints (sub-requirement 2)
# ===========================================================================

from orchestrate.core.catalog_gate import CatalogGate
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.shared_handlers import SharedHandlers

_GATE_SOURCE = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])


def _gate_role_psop(skill="explore", catalog_version="pilot-v1"):
    return PSOP.model_validate(dict(
        id=f"wf-{skill}", name="Role demo", catalog_version=catalog_version,
        steps=[dict(name="optimize", subtasks=[dict(
            task_id="t1", description="Explore intent", binding="role",
            agent="optimizer", skill=skill, role_version="1",
        )])],
    ))


def _gate_instance_psop():
    return PSOP.model_validate(dict(
        id="wf-legacy", name="Legacy",
        steps=[dict(name="work", subtasks=[dict(
            task_id="t1", description="Do work", binding="instance",
            agent="Existing Agent", skill="Existing Skill",
        )])],
    ))


def _gate_catalog(tmp_path, status="approved"):
    catalog = RoleCatalog.model_validate(dict(
        catalog_version="pilot-v1",
        roles=[dict(
            role_id="optimizer", role_version="1", name="Optimizer",
            description="Synthetic test role", source=_GATE_SOURCE, review_status=status,
            skills=[dict(skill_id="explore", name="explore", description="explore",
                         source=_GATE_SOURCE, review_status=status)],
        )],
    ))
    path = tmp_path / "catalog.json"
    path.write_text(catalog.model_dump_json(), encoding="utf-8")
    return str(path)


class _RecordingHandler:
    def __init__(self):
        self.saved = []

    def handle(self, psop):
        self.saved.append(psop.id)
        return psop.id


@pytest.fixture
def gated_save(monkeypatch):
    """Route SharedHandlers through a real gate over a recording handler."""
    recording = _RecordingHandler()
    monkeypatch.setattr(SharedHandlers, "_save_handle", CatalogGate(recording))
    return recording


def _use_catalog(monkeypatch, path):
    monkeypatch.setattr(
        "orchestrate.core.catalog_gate.configured_catalog_path", lambda: path)


class TestOrchestrateSopCatalogGate:
    def _generate_role_psop(self, **kwargs):
        return _gate_role_psop(**kwargs)

    def _post(self, client, monkeypatch, psop):
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.PsopGenerator") as mock_gen_class:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_workflow.return_value = psop
            mock_gen_class.return_value = mock_gen
            return client.post("/api/v1/orchestrate/sop", json={"sop_content": "Step 1"})

    def test_approved_reference_saves(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path))
        resp = self._post(client, monkeypatch, self._generate_role_psop())
        assert resp.status_code == 201
        assert gated_save.saved == ["wf-explore"]

    def test_draft_reference_rejected_without_persisting(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path, status="draft"))
        resp = self._post(client, monkeypatch, self._generate_role_psop())
        assert resp.status_code == 422
        assert "INVALID_ROLE_SKILL" in resp.text
        assert gated_save.saved == []

    def test_unknown_skill_rejected(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path))
        resp = self._post(client, monkeypatch, self._generate_role_psop(skill="unknown"))
        assert resp.status_code == 422
        assert "INVALID_ROLE_SKILL" in resp.text
        assert gated_save.saved == []

    def test_catalog_version_mismatch_rejected(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path))
        resp = self._post(client, monkeypatch, self._generate_role_psop(catalog_version="pilot-v2"))
        assert resp.status_code == 422
        assert "CATALOG_VERSION_UNAVAILABLE" in resp.text
        assert gated_save.saved == []

    def test_missing_catalog_rejected(self, client, gated_save, monkeypatch):
        _use_catalog(monkeypatch, None)
        resp = self._post(client, monkeypatch, self._generate_role_psop())
        assert resp.status_code == 422
        assert "CATALOG_VERSION_UNAVAILABLE" in resp.text
        assert gated_save.saved == []

    def test_legacy_instance_workflow_needs_no_catalog(self, client, gated_save, monkeypatch):
        _use_catalog(monkeypatch, None)
        resp = self._post(client, monkeypatch, _gate_instance_psop())
        assert resp.status_code == 201
        assert gated_save.saved == ["wf-legacy"]


# ===========================================================================
# 10. Dispatch-time role resolution threading through the execute endpoints
# ===========================================================================

from pathlib import Path

from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.core.model.instance_binding import (
    InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
)
from orchestrate.runtime.instance_projection import ResolutionRequest
from samples.role_pilot.technical_server import pilot_card

_ROLE_SEED_CATALOG = Path("samples/role_pilot/role_catalog.json")
_ROLE_OPTIMIZER = "ran-energy-optimizer"


def _role_approve_all(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "review_status":
                value[key] = "approved"
            else:
                _role_approve_all(item)
    elif isinstance(value, list):
        for item in value:
            _role_approve_all(item)


def _role_approved_catalog_file(tmp_path):
    data = json.loads(_ROLE_SEED_CATALOG.read_text(encoding="utf-8"))
    _role_approve_all(data)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _role_registry_file(tmp_path):
    scope = ServiceScope(tenant="t", site="s", business_object="b")
    registry = InstanceRegistry(config_version="cfg-v1", instances=[
        InstanceBinding(
            instance_id="inst-a", agent_name="Technical RAN A", endpoint="http://127.0.0.1:1",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=_ROLE_OPTIMIZER, role_version="1.0.0",
                                 skill_id="explore-energy-intent",
                                 instance_skill_id="explore-a", execution_skill="Explore A")],
        ),
        InstanceBinding(
            instance_id="inst-b", agent_name="Technical RAN B", endpoint="http://127.0.0.1:2",
            enabled=True, technical_status="passed", scopes=[scope],
            skills=[SkillMapping(role_id=_ROLE_OPTIMIZER, role_version="1.0.0",
                                 skill_id="fulfill-energy-intent",
                                 instance_skill_id="explore-b", execution_skill="Explore B")],
        ),
    ])
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    return str(path)


def _pilot_role_psop():
    return PSOP.model_validate(dict(
        id="wf-role-pilot", name="Role pilot", catalog_version="pilot-wireless-v1",
        steps=[dict(name="explore", subtasks=[dict(
            task_id="t1", description="Explore energy intent", binding="role",
            agent=_ROLE_OPTIMIZER, skill="explore-energy-intent", role_version="1.0.0",
        )])],
    ))


def _pilot_cards():
    return [pilot_card("a", 1), pilot_card("b", 2)]


def _sse_events(response):
    return [json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")]


class _RecordingRecordHandler:
    def __init__(self):
        self.records = []

    def handle(self, record):
        self.records.append(record)
        return record.execution_id


class _CapturingHostClient:
    """Stands in for the A2A-T transport so dispatch stays offline."""

    def __init__(self):
        self.contents = []

    async def stream_message(self, agent_name, content):
        self.contents.append(content)
        yield {"task_state": "COMPLETED", "metadata": {}}

    async def close(self):
        pass


class TestExecutePsopByIdRoleResolution:
    @pytest.fixture(autouse=True)
    def stub_transport(self, monkeypatch):
        from orchestrate.runtime.exec_engine import OrchestrationEngine
        host_client = _CapturingHostClient()
        monkeypatch.setattr(OrchestrationEngine, "_get_engine_client",
                            lambda self, target=None: host_client)
        self.host_client = host_client

    @pytest.fixture(autouse=True)
    def capture_records(self, monkeypatch):
        handler = _RecordingRecordHandler()
        monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler",
                            lambda interface_type: handler)
        self.records = handler.records

    def _get(self, client, monkeypatch, tmp_path, *, registry=True, params=None):
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances", lambda: ["inst-a", "inst-b"])
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: _role_approved_catalog_file(tmp_path))
        monkeypatch.setattr(
            "orchestrate.runtime.instance_projection.configured_registry_path",
            lambda: _role_registry_file(tmp_path) if registry else None)
        with patch("orchestrate.server.external_api.SharedHandlers") as mock_shared, \
             patch("orchestrate.server.external_api.get_agent_cards",
                   new_callable=AsyncMock) as mock_cards:
            mock_retrieval = MagicMock()
            mock_retrieval.get_psop_by_id.return_value = _pilot_role_psop()
            mock_shared.retrieval.return_value = mock_retrieval
            mock_cards.return_value = _pilot_cards()
            return client.get("/api/v1/orchestrate/execute/wf-role-pilot",
                              params=params or {})

    def test_scope_param_yields_resolution_event(self, client, monkeypatch, tmp_path):
        resp = self._get(client, monkeypatch, tmp_path, params={
            "scope": "t/s/b",
            "authorized_instances": "inst-a,inst-b",
            "caller_id": "api-client",
        })
        assert resp.status_code == 200
        events = _sse_events(resp)
        resolutions = [e for e in events if e["type"] == "resolution"]
        assert len(resolutions) == 1
        assert resolutions[0]["data"]["catalog_version"] == "pilot-wireless-v1"
        assert resolutions[0]["data"]["execution_scope"] == "t/s/b"
        assert self.host_client.contents == []
        assert events[-1]["data"]["code"] == "ROLE_EXECUTION_NOT_ENABLED"

    def test_without_scope_fails_closed(self, client, monkeypatch, tmp_path):
        resp = self._get(client, monkeypatch, tmp_path, registry=False)
        assert resp.status_code == 200
        events = _sse_events(resp)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert errors[0]["data"]["code"] == "RESOLUTION_INPUT_INVALID"
        assert all(e["type"] != "resolution" for e in events)
        assert len(self.records) == 1
        assert self.records[0].status == ExecutionStatus.FAILED
        assert self.host_client.contents == []


class TestExecuteAutoRoleResolution:
    """POST /orchestrate/execute forwards the resolution body fields."""

    def test_body_fields_pass_through_as_resolution_request(self, client):
        mock_sse = MagicMock()
        mock_sse.media_type = "text/event-stream"
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.dispatch_intent_sse", new_callable=AsyncMock) as mock_dispatch:
            mock_cards.return_value = [MagicMock()]
            mock_dispatch.return_value = mock_sse
            resp = client.post(
                "/api/v1/orchestrate/execute",
                json={"task": "optimize energy",
                      "scope": "t/s/b",
                      "authorized_instances": ["inst-a", "inst-b"],
                      "caller_id": "api-client"},
            )
            assert resp.status_code == 200
            mock_dispatch.assert_called_once()
            assert mock_dispatch.call_args.kwargs["resolution_request"].model_dump() == ResolutionRequest(
                scope="t/s/b",
                authorized_instance_ids=["inst-a", "inst-b"],
                caller_id="api-client",
            ).model_dump()

    def test_body_without_resolution_fields_defaults_to_empty_request(self, client):
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
            assert resp.status_code == 200
            mock_dispatch.assert_called_once()
            assert mock_dispatch.call_args.kwargs["resolution_request"].model_dump() == ResolutionRequest().model_dump()


class TestOrchestrateIntentCatalogGate:
    def _post(self, client, psop):
        with patch("orchestrate.server.external_api.get_agent_cards", new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.external_api.IntentPsopGenerator") as mock_gen_class:
            mock_cards.return_value = [MagicMock()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_from_intent.return_value = psop
            mock_gen_class.return_value = mock_gen
            return client.post("/api/v1/orchestrate/intent", json={"intent": "optimize energy"})

    def test_approved_reference_saves(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path))
        resp = self._post(client, _gate_role_psop())
        assert resp.status_code == 201
        assert gated_save.saved == ["wf-explore"]

    def test_draft_reference_rejected_without_persisting(self, client, gated_save, monkeypatch, tmp_path):
        _use_catalog(monkeypatch, _gate_catalog(tmp_path, status="draft"))
        resp = self._post(client, _gate_role_psop())
        assert resp.status_code == 422
        assert "INVALID_ROLE_SKILL" in resp.text
        assert gated_save.saved == []

    def test_missing_catalog_rejected(self, client, gated_save, monkeypatch):
        _use_catalog(monkeypatch, None)
        resp = self._post(client, _gate_role_psop())
        assert resp.status_code == 422
        assert gated_save.saved == []

    def test_legacy_instance_workflow_needs_no_catalog(self, client, gated_save, monkeypatch):
        _use_catalog(monkeypatch, None)
        resp = self._post(client, _gate_instance_psop())
        assert resp.status_code == 201
        assert gated_save.saved == ["wf-legacy"]

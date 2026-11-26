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

# tests/test_frontend_support_server.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO
import json
from pathlib import Path
from fastapi.testclient import TestClient

from a2a.types import AgentCard

import httpx

from orchestrate.core.catalog_gate import CatalogGate
from orchestrate.core.model.execution_record import ExecutionStatus
from orchestrate.core.model.instance_binding import (
    InstanceBinding, InstanceRegistry, ServiceScope, SkillMapping,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.server.frontend_support_server import app


BASE = "/rest/v1/orchestrate"


@pytest.fixture
def client(account_session):
    """Create FastAPI test client"""
    with TestClient(app, headers=account_session) as client:
        yield client


@pytest.fixture
def mock_storage():
    """Mock SharedHandlers save/delete"""
    with patch('orchestrate.core.shared_handlers.SharedHandlers.save_psop'), \
         patch('orchestrate.core.shared_handlers.SharedHandlers.delete_psop'):
        yield


@pytest.fixture
def mock_retrieval():
    """Mock WorkflowRetrieval via SharedHandlers"""
    with patch('orchestrate.core.shared_handlers.SharedHandlers.retrieval') as mock:
        inner = MagicMock()
        mock.return_value = inner
        yield inner


@pytest.fixture
def mock_agent_lib():
    """Mock AgentRegistryClient (used internally by get_agent_cards)"""
    with patch('orchestrate.server.frontend_support_server.get_agent_cards', return_value=[]) as mock:
        yield mock


@pytest.fixture
def mock_parser():
    """Mock SolutionPackageParser"""
    from orchestrate.solution_package.parse_flow import SolutionPackageParser
    select_title = SolutionPackageParser.select_chapter_title
    with patch('orchestrate.server.frontend_support_server.SolutionPackageParser') as MockParser:
        MockParser.select_chapter_title.side_effect = select_title
        mock_instance = MockParser.return_value
        yield mock_instance


class TestParsePdfEndpoint:
    """Test /parse-pdf endpoint"""

    def test_parse_pdf_missing_file(self, client):
        """Test missing file"""
        response = client.post(f'{BASE}/parse-pdf')
        assert response.status_code == 422

    def test_parse_pdf_empty_filename(self, client):
        """Test empty filename.

        httpx's files= helper drops an empty filename from the multipart
        Content-Disposition header entirely, so the body is written by hand to
        keep filename="" explicit. Which layer rejects that explicit empty name
        depends on the multipart implementation: Starlette up to 1.8 passes it to
        the handler, whose own `if not file.filename` answers 400, while Starlette
        1.9 treats it as a missing upload and multipart validation answers 422
        before the handler runs. Both refuse the request, so assert the rejection
        rather than the layer that produced it.
        """
        body = (
            b'--boundary123\r\n'
            b'Content-Disposition: form-data; name="file"; filename=""\r\n'
            b'Content-Type: application/octet-stream\r\n\r\n'
            b'\r\n'
            b'--boundary123--\r\n'
        )
        response = client.post(
            f'{BASE}/parse-pdf',
            content=body,
            headers={'Content-Type': 'multipart/form-data; boundary=boundary123'},
        )
        assert response.status_code in (400, 422)
        if response.status_code == 400:
            assert 'Filename is required' in response.json()['message']

    def test_parse_pdf_wrong_extension(self, client):
        """Test non-PDF file"""
        response = client.post(f'{BASE}/parse-pdf', files={
            'file': ('test.txt', BytesIO(b'test'))
        })
        assert response.status_code == 400
        data = response.json()
        assert 'Invalid filename format' in data['message']

    def test_parse_pdf_not_pdf_content(self, client):
        """Test a .pdf-named file whose content isn't a real PDF"""
        response = client.post(f'{BASE}/parse-pdf', files={
            'file': ('test.pdf', BytesIO(b'not a pdf'))
        })
        assert response.status_code == 400
        assert 'not a valid PDF' in response.json()['message']

    def test_parse_pdf_success(self, client, mock_parser, tmp_path, monkeypatch):
        """Test successful PDF parsing: all chapters stored, chapter 5 -> PreFlow"""
        monkeypatch.setattr(
            "orchestrate.server.frontend_support_server.solution_package_manager.storage_dir",
            tmp_path,
        )
        mock_parser.parse_pdf_all_chapters.return_value = {
            '5. Interaction Flow': '# Test Markdown',
            '1. Overview': 'overview content',
        }

        response = client.post(f'{BASE}/parse-pdf', files={
            'file': ('test.pdf', BytesIO(b'%PDF-1.4 test'))
        })

        assert response.status_code == 200
        assert response.json()['data']['steps_md'] == "# Test Markdown"
        # the manager strips the .pdf extension when storing
        stored = json.loads((tmp_path / 'test.json').read_text(encoding='utf-8'))
        assert stored['chapters']['1. Overview'] == 'overview content'
        assert 'workflow_id' not in stored

    def test_parse_pdf_parse_failure(self, client, mock_parser):
        """Test parsing failure (no chapters extracted)"""
        mock_parser.parse_pdf_all_chapters.return_value = {}

        response = client.post(f'{BASE}/parse-pdf', files={
            'file': ('test.pdf', BytesIO(b'%PDF-1.4 test'))
        })

        assert response.status_code == 400
        assert 'No chapters found in PDF' in response.json()['message']


class TestPlanEndpoint:
    """Test /plan endpoint"""

    def test_plan_empty_content(self, client):
        """Test empty request body"""
        response = client.post(f'{BASE}/generate-from-preflow')
        assert response.status_code == 422

    @pytest.mark.skip(reason='Plan endpoint tests are temporarily disabled')
    def test_plan_empty_body(self, client):
        """Test empty request body"""
        response = client.post(f'{BASE}/generate-from-preflow', json={})
        assert response.status_code == 400

    @pytest.mark.skip(reason='Plan endpoint tests are temporarily disabled')
    def test_plan_missing_fields(self, client):
        """Test missing required fields"""
        response = client.post(f'{BASE}/generate-from-preflow', json={"preflow": {}})
        assert response.status_code == 400

    @pytest.mark.skip(reason='Plan endpoint tests are temporarily disabled')
    def test_plan_success(self, client, mock_storage):
        """Test successful planning"""
        with patch('orchestrate.server.frontend_support_server.PsopGenerator') as MockGen, \
                patch('orchestrate.server.frontend_support_server.PreFlow') as MockPreFlow, \
                patch('orchestrate.server.frontend_support_server.AgentCard') as MockCard:
            mock_gen = MockGen.return_value
            mock_workflow = MagicMock()
            mock_workflow.model_dump_json.return_value = '{"id": "123"}'
            mock_gen.generate_psop_workflow.return_value = mock_workflow
            mock_storage.save_psop.return_value = "123"

            MockPreFlow.model_validate.return_value = MagicMock()
            MockCard.model_validate.return_value = MagicMock()

            response = client.post(f'{BASE}/generate-from-preflow', json={
                "preflow": {"name": "test", "description": "desc", "steps_md": "# test"},
                "agent_cards": [{"name": "agent1"}]
            })

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'


class TestPsopsEndpoints:
    """Test /psops related endpoints"""

    @pytest.mark.skip(reason='PSOP CRUD endpoint tests are temporarily disabled')
    def test_get_psops_list(self, client, mock_retrieval):
        """Test getting PSOP list"""
        mock_wf = MagicMock()
        mock_wf.to_dict.return_value = {"id": "123", "name": "test"}
        mock_retrieval.list_recent_workflows.return_value = [mock_wf]

        response = client.get('/psops?limit=5&workflow_type=psop')
        assert response.status_code == 200
        data = response.json()
        assert data['count'] == 1

    @pytest.mark.skip(reason='PSOP CRUD endpoint tests are temporarily disabled')
    def test_get_psop_by_id_found(self, client, mock_retrieval):
        """Test getting existing PSOP by ID"""
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = {"id": "123", "name": "test"}
        mock_retrieval.get_psop_by_id.return_value = mock_psop

        response = client.get('/psops/123')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'

    def test_get_psop_by_id_not_found(self, client, mock_retrieval):
        """Test getting nonexistent PSOP by ID"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.get('/psops/nonexistent')
        assert response.status_code == 404

    @pytest.mark.skip(reason='PSOP CRUD endpoint tests are temporarily disabled')
    def test_save_psop_success(self, client, mock_storage):
        """Test saving PSOP"""
        with patch('orchestrate.server.frontend_support_server.PSOP') as MockPSOP:
            mock_psop = MagicMock()
            mock_psop.model_dump.return_value = {"id": "123"}
            MockPSOP.model_validate.return_value = mock_psop
            mock_storage.save_psop.return_value = "123"

            response = client.post('/psops', json={"id": "123", "name": "test"})

            assert response.status_code == 201

    @pytest.mark.skip(reason='PSOP CRUD endpoint tests are temporarily disabled')
    def test_delete_psop_success(self, client, mock_retrieval, mock_storage):
        """Test deleting PSOP"""
        mock_psop = MagicMock()
        mock_retrieval.get_psop_by_id.return_value = mock_psop
        mock_storage.delete_psop.return_value = True

        response = client.delete('/psops/123')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'

    def test_delete_psop_not_found(self, client, mock_retrieval):
        """Test deleting nonexistent PSOP"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.delete('/psops/nonexistent')
        assert response.status_code == 404


class TestWorkflowBpmnEndpoint:
    """GET /workflows/{id}/bpmn -- PSOP retrieved via the normal query path,
    converted to BPMN 2.0 XML for the frontend export button."""

    BASE_URL = f'{BASE}/workflows'

    @staticmethod
    def _real_psop():
        from orchestrate.core.model.psop import PSOP, Step, Task, JumpCondition
        return PSOP(
            id="wf-bpmn-internal",
            name="内部导出流程",
            steps=[
                Step(name="step1", subtasks=[Task(description="t1", agent="a1", skill="s1")],
                     next=[JumpCondition(step="step2", condition="")]),
                Step(name="step2", subtasks=[Task(description="t2", agent="a2", skill="s2")]),
            ],
        )

    def test_get_workflow_bpmn_success(self, client, mock_retrieval):
        mock_retrieval.get_psop_by_id.return_value = self._real_psop()

        response = client.get(f'{self.BASE_URL}/wf-bpmn-internal/bpmn')
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('application/xml')
        disposition = response.headers.get('content-disposition', '')
        assert '.bpmn' in disposition
        # Chinese workflow names cannot travel in a latin-1 header: they ride
        # the RFC 5987 filename* parameter, with an ASCII fallback alongside.
        assert "filename*=UTF-8''" in disposition
        assert response.text.startswith('<?xml version="1.0"')
        assert '<bpmn:process' in response.text
        assert '<bpmn:task' in response.text

    def test_get_workflow_bpmn_not_found(self, client, mock_retrieval):
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.get(f'{self.BASE_URL}/nonexistent/bpmn')
        assert response.status_code == 404

    def test_get_workflow_bpmn_conversion_error(self, client, mock_retrieval):
        """A PSOP without steps cannot be converted -> 500."""
        mock_retrieval.get_psop_by_id.return_value = self._real_psop().model_copy(update={"steps": []})

        response = client.get(f'{self.BASE_URL}/wf-empty/bpmn')
        assert response.status_code == 500

    def test_get_workflow_bpmn_retrieval_error(self, client, mock_retrieval):
        mock_retrieval.get_psop_by_id.side_effect = RuntimeError('db down')

        response = client.get(f'{self.BASE_URL}/err-id/bpmn')
        assert response.status_code == 500


class TestAgentCardsEndpoint:
    """Test /agent-cards endpoint"""

    @pytest.fixture(autouse=True)
    def mock_agent_cards_semaphore(self):
        """Mock agent_cards_semaphore to prevent blocking in tests"""
        mock_sem = MagicMock()
        with patch('orchestrate.server.frontend_support_server.agent_cards_semaphore', mock_sem):
            yield mock_sem

    def test_get_agent_cards_success(self, client, mock_agent_lib):
        """Test successfully getting AgentCard list"""
        mock_card = MagicMock()
        mock_agent_lib.return_value = [mock_card]

        with patch('orchestrate.server.frontend_support_server.MessageToDict') as mock_msg:
            mock_msg.return_value = {"name": "agent1", "url": "http://test"}

            response = client.get('/rest/v1/orchestrate/agent-cards')
            assert response.status_code == 200
            data = response.json()
            assert data['data'][0]['name'] == 'agent1'

    def test_get_agent_cards_config_not_found(self, client, mock_agent_lib):
        """Test config file not found"""
        mock_agent_lib.side_effect = FileNotFoundError("config not found")

        response = client.get('/rest/v1/orchestrate/agent-cards')
        assert response.status_code == 404

    def test_get_agent_cards_value_error(self, client, mock_agent_lib):
        """Test data format error"""
        mock_agent_lib.side_effect = ValueError("invalid format")

        response = client.get('/rest/v1/orchestrate/agent-cards')
        assert response.status_code == 400


AGENT_CARD_PAYLOAD = {
    "name": "AgentA",
    "version": "1.0.0",
    "description": "demo agent",
    "provider": {"organization": "OrgA", "url": "http://localhost:8080"},
    "skills": [{"id": "s1", "name": "skill1", "description": "d"}],
}


def _http_status_error(status_code, message="Agent not found"):
    req = httpx.Request('PUT', 'http://registry/agent-cards')
    resp = httpx.Response(status_code, request=req,
                          json={"errors": {"error": [{"errorMessage": message}]}})
    return httpx.HTTPStatusError(message, request=req, response=resp)


class TestAgentCardWriteEndpoints:
    """Test admin PUT/DELETE /agent-cards/{organization}/{name} proxy endpoints"""

    @pytest.fixture(autouse=True)
    def mock_write_semaphore(self):
        mock_sem = MagicMock()
        with patch('orchestrate.server.frontend_support_server.agent_card_write_semaphore', mock_sem):
            yield mock_sem

    @pytest.fixture
    def mock_registry_client(self):
        with patch('orchestrate.server.frontend_support_server.AgentRegistryClientFactory') as mock_factory:
            client_mock = MagicMock()
            client_mock.update_full = AsyncMock(return_value={"results": []})
            client_mock.deregister = AsyncMock(return_value={"deleted": True})
            client_mock.close = AsyncMock(return_value=None)
            mock_factory.return_value.create_from_env.return_value = client_mock
            yield client_mock

    def test_update_agent_card_success(self, client, mock_registry_client):
        """Test successful card update via the registry proxy"""
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json=AGENT_CARD_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert data['code'] == 200
        assert data['data']['updated'] is True
        mock_registry_client.update_full.assert_awaited_once()
        # agent-level signatures must never be forwarded: the edited content
        # invalidates them, and the registry re-signs when signing is enabled
        forwarded = mock_registry_client.update_full.await_args.args[2]
        assert len(forwarded.signatures) == 0

    def test_update_agent_card_name_mismatch(self, client, mock_registry_client):
        """Body identity must match the URL path, or the registry would re-key"""
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json={
            **AGENT_CARD_PAYLOAD, "name": "Other",
        })
        assert response.status_code == 400
        mock_registry_client.update_full.assert_not_awaited()

    def test_update_agent_card_org_mismatch(self, client, mock_registry_client):
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json={
            **AGENT_CARD_PAYLOAD,
            "provider": {"organization": "Other", "url": "http://localhost:8080"},
        })
        assert response.status_code == 400

    def test_update_agent_card_invalid_payload(self, client, mock_registry_client):
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json=["not", "a", "dict"])
        assert response.status_code == 400

    def test_update_agent_card_registry_not_found(self, client, mock_registry_client):
        mock_registry_client.update_full.side_effect = _http_status_error(404)
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json=AGENT_CARD_PAYLOAD)
        assert response.status_code == 404
        assert 'Agent not found' in response.json()['message']

    def test_update_agent_card_registry_validation_error(self, client, mock_registry_client):
        mock_registry_client.update_full.side_effect = _http_status_error(422, "invalid url")
        response = client.put(f'{BASE}/agent-cards/OrgA/AgentA', json=AGENT_CARD_PAYLOAD)
        assert response.status_code == 400
        assert 'invalid url' in response.json()['message']

    def test_delete_agent_card_success(self, client, mock_registry_client):
        response = client.delete(f'{BASE}/agent-cards/OrgA/AgentA')
        assert response.status_code == 200
        data = response.json()
        assert data['code'] == 200
        assert data['data']['deleted'] is True
        mock_registry_client.deregister.assert_awaited_once_with("AgentA", "OrgA")

    def test_delete_agent_card_registry_not_found(self, client, mock_registry_client):
        mock_registry_client.deregister.side_effect = _http_status_error(404)
        response = client.delete(f'{BASE}/agent-cards/OrgA/AgentA')
        assert response.status_code == 404


class TestIntentEndpoints:
    """Test intent-related endpoints"""

    @pytest.fixture(autouse=True)
    def mock_agent_cards_semaphore(self):
        """Mock agent_cards_semaphore to prevent blocking in tests"""
        mock_sem = MagicMock()
        with patch('orchestrate.server.frontend_support_server.agent_cards_semaphore', mock_sem):
            yield mock_sem

    def test_generate_from_intent_success(self, client, mock_agent_lib):
        """Test generating PSOP from intent successfully"""
        mock_card = MagicMock()
        mock_card.model_dump.return_value = {"name": "agent1"}
        mock_agent_lib.return_value = [mock_card]

        with patch('orchestrate.server.frontend_support_server.IntentPsopGenerator') as MockGen:
            mock_gen = MockGen.return_value
            mock_psop = MagicMock()
            mock_psop.model_dump.return_value = {"id": "123", "name": "generated"}
            mock_gen.generate_psop_from_intent.return_value = mock_psop

            response = client.post(f'{BASE}/generate-from-intent', json={
                "user_intent": "Create a workflow for me"
            })

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'

    def test_generate_from_intent_missing_intent(self, client):
        """Test missing user_intent field"""
        response = client.post(f'{BASE}/generate-from-intent', json={})
        assert response.status_code == 422

    def test_retrieve_by_intent_success(self, client, mock_retrieval):
        """Test successful retrieval by intent"""
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = {"id": "123", "name": "matched"}
        mock_psop.id = "123"
        mock_psop.name = "matched"
        mock_retrieval.retrieve_psop_by_intent.return_value = mock_psop

        response = client.post(f'{BASE}/retrieve-by-intent', json={
            "user_intent": "Find workflow"
        })

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'

    def test_retrieve_by_intent_no_match(self, client, mock_retrieval):
        """Test retrieval by intent with no match"""
        mock_retrieval.retrieve_psop_by_intent.return_value = None

        response = client.post(f'{BASE}/retrieve-by-intent', json={
            "user_intent": "Not found"
        })

        assert response.status_code == 200
        data = response.json()
        assert data['data'] is None or data['data'] == {}


class TestStartProcessStreamEndpoint:
    """Test /execute endpoint"""

    def test_stream_missing_psop_id(self, client):
        """Test missing psop_id parameter"""
        response = client.get(f'{BASE}/execute')
        assert response.status_code == 422

    def test_stream_psop_not_found(self, client, mock_retrieval):
        """Test PSOP not found"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.get(f'{BASE}/execute?psop_id=nonexistent')
        assert response.status_code == 404

    def test_stream_no_agent_cards(self, client, mock_retrieval, mock_agent_lib):
        """Test no available AgentCards"""
        mock_psop = MagicMock()
        mock_psop.id = "123"
        mock_psop.name = "test_workflow"
        mock_psop.steps = []
        mock_retrieval.get_psop_by_id.return_value = mock_psop
        mock_agent_lib.return_value = []

        response = client.get(f'{BASE}/execute?psop_id=123')
        assert response.status_code == 200




# ===========================================================================
# Catalog gate on /generate-from-intent (sub-requirement 2)
# ===========================================================================

_GATE_SOURCE = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])


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


def _gate_role_psop():
    return PSOP.model_validate(dict(
        id="wf-explore", name="Role demo", catalog_version="pilot-v1",
        steps=[dict(name="optimize", subtasks=[dict(
            task_id="t1", description="Explore intent", binding="role",
            agent="optimizer", skill="explore", role_version="1",
        )])],
    ))


class _RecordingHandler:
    def __init__(self):
        self.saved = []

    def handle(self, psop):
        self.saved.append(psop.id)
        return psop.id


class _ExplodingHandler:
    def handle(self, psop):
        raise RuntimeError("storage down")


class TestGenerateFromIntentCatalogGate:
    def _post(self, client, monkeypatch, generated_psop, save_handler):
        monkeypatch.setattr(SharedHandlers, "_save_handle", save_handler)
        with patch("orchestrate.server.frontend_support_server.get_agent_cards",
                   new_callable=AsyncMock) as mock_cards, \
             patch("orchestrate.server.frontend_support_server.IntentPsopGenerator") as mock_gen_class:
            mock_cards.return_value = [AgentCard()]
            mock_gen = MagicMock()
            mock_gen.generate_psop_from_intent.return_value = generated_psop
            mock_gen_class.return_value = mock_gen
            return client.post(
                f"{BASE}/generate-from-intent", json={"user_intent": "optimize energy"})

    def test_unauthorized_role_psop_is_422_not_success(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: _gate_catalog(tmp_path, status="draft"))
        recording = _RecordingHandler()
        resp = self._post(client, monkeypatch, _gate_role_psop(),
                          CatalogGate(recording))
        assert resp.status_code == 422
        assert "INVALID_ROLE_SKILL" in resp.text
        assert recording.saved == []

    def test_missing_catalog_rejects_role_psop(self, client, monkeypatch):
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path", lambda: None)
        recording = _RecordingHandler()
        resp = self._post(client, monkeypatch, _gate_role_psop(),
                          CatalogGate(recording))
        assert resp.status_code == 422
        assert "CATALOG_VERSION_UNAVAILABLE" in resp.text
        assert recording.saved == []

    def test_approved_role_psop_saves_and_returns_result(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: _gate_catalog(tmp_path))
        recording = _RecordingHandler()
        resp = self._post(client, monkeypatch, _gate_role_psop(),
                          CatalogGate(recording))
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "wf-explore"
        assert recording.saved == ["wf-explore"]

    def test_generic_auto_save_failure_still_returns_result(self, client, monkeypatch, tmp_path):
        """Plain storage failures keep the existing non-fatal behavior:
        the gate passes (approved catalog) and the storage handler itself
        fails with a generic error."""
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: _gate_catalog(tmp_path))
        resp = self._post(client, monkeypatch, _gate_role_psop(), _ExplodingHandler())
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "wf-explore"


# ===========================================================================
# GET /execute: dispatch-time role resolution threading (sub-requirement 4)
# ===========================================================================

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
    from samples.role_pilot.technical_server import pilot_card
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


class TestExecuteRoleResolution:
    """GET /execute threads scope/authorized/caller into role resolution,
    the SSE body carries the resolution evidence, and the saved execution
    record captures it. Fail-closed when the registry is unconfigured."""

    @pytest.fixture(autouse=True)
    def stub_transport(self, monkeypatch):
        from orchestrate.runtime.exec_engine import OrchestrationEngine
        client = _CapturingHostClient()
        monkeypatch.setattr(OrchestrationEngine, "_get_engine_client", lambda self: client)
        self.host_client = client

    @pytest.fixture(autouse=True)
    def capture_records(self, monkeypatch):
        handler = _RecordingRecordHandler()
        monkeypatch.setattr("orchestrate.handlers.dispatch.get_storage_handler",
                            lambda interface_type: handler)
        self.records = handler.records

    @pytest.fixture(autouse=True)
    def role_retrieval(self, mock_retrieval):
        mock_retrieval.get_psop_by_id.return_value = _pilot_role_psop()

    def _dispatch(self, client, monkeypatch, tmp_path, *, registry=True, params=None):
        monkeypatch.setattr("orchestrate.runtime.instance_projection.configured_authorized_instances", lambda: ["inst-a", "inst-b"])
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: _role_approved_catalog_file(tmp_path))
        monkeypatch.setattr(
            "orchestrate.runtime.instance_projection.configured_registry_path",
            lambda: _role_registry_file(tmp_path) if registry else None)
        with patch("orchestrate.server.frontend_support_server.get_agent_cards",
                   new_callable=AsyncMock) as mock_cards:
            mock_cards.return_value = _pilot_cards()
            query = {"psop_id": "wf-role-pilot"}
            query.update(params or {})
            return client.get(f"{BASE}/execute", params=query)

    def test_scope_params_resolve_and_capture_evidence(self, client, monkeypatch, tmp_path):
        response = self._dispatch(client, monkeypatch, tmp_path, params={
            "scope": "t/s/b",
            "authorized_instances": "inst-a,inst-b",
            "caller_id": "endpoint-test",
        })
        assert response.status_code == 200

        events = _sse_events(response)
        resolutions = [e for e in events if e["type"] == "resolution"]
        assert len(resolutions) == 1
        resolution = resolutions[0]["data"]
        assert resolution["catalog_version"] == "pilot-wireless-v1"
        assert resolution["execution_scope"] == "t/s/b"

        psop_updates = [e for e in events if e["type"] == "psop_update"]
        assert psop_updates
        final_psop = psop_updates[-1]["data"]["psop"]
        assert all(task["binding"] == "instance"
                   for step in final_psop["steps"] for task in step["subtasks"])

        assert len(self.records) == 1
        record = self.records[0]
        assert record.catalog_version == "pilot-wireless-v1"
        assert record.execution_scope == "t/s/b"
        assert record.bindings
        assert record.card_fingerprints
        assert record.execution_id == resolution["execution_id"]

        assert self.host_client.contents == []
        assert events[-1]["data"]["code"] == "ROLE_EXECUTION_NOT_ENABLED"
        assert record.status == ExecutionStatus.FAILED
        assert record.resolution_snapshot["context"]["caller_id"] == "fixture-admin"
        assert record.resolution_snapshot["bindings"][0]["selection_reason"]
        assert record.template_fingerprint == resolution["template_fingerprint"]

    def test_without_registry_fails_closed(self, client, monkeypatch, tmp_path):
        response = self._dispatch(client, monkeypatch, tmp_path, registry=False, params={
            "scope": "t/s/b",
            "authorized_instances": "inst-a,inst-b",
        })
        assert response.status_code == 200

        events = _sse_events(response)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert errors[0]["data"]["code"] == "RESOLUTION_INPUT_INVALID"
        assert all(e["type"] != "resolution" for e in events)

        assert len(self.records) == 1
        record = self.records[0]
        assert record.status == ExecutionStatus.FAILED
        assert not record.bindings
        assert not record.catalog_version
        # Fail-closed: nothing reached transport.
        assert self.host_client.contents == []

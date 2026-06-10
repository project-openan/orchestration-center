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
from unittest.mock import patch, MagicMock
from io import BytesIO
from fastapi.testclient import TestClient

import os

_prev_testing = os.environ.get('TESTING')
os.environ['TESTING'] = 'True'

from orchestrate.server.frontend_support_server import app


def _cleanup_testing_env():
    if _prev_testing is not None:
        os.environ['TESTING'] = _prev_testing
    else:
        os.environ.pop('TESTING', None)


import atexit
atexit.register(_cleanup_testing_env)

BASE = "/rest/v1/orchestrate"


@pytest.fixture
def client():
    """Create FastAPI test client"""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_storage():
    """Mock SharedHandlers save/delete"""
    with patch('orchestrate.server.shared_handlers.SharedHandlers.save_psop'), \
         patch('orchestrate.server.shared_handlers.SharedHandlers.delete_psop'):
        yield


@pytest.fixture
def mock_retrieval():
    """Mock WorkflowRetrieval via SharedHandlers"""
    with patch('orchestrate.server.shared_handlers.SharedHandlers.retrieval') as mock:
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
    with patch('orchestrate.server.frontend_support_server.SolutionPackageParser') as MockParser:
        mock_instance = MockParser.return_value
        yield mock_instance


class TestParsePdfEndpoint:
    """Test /parse-pdf endpoint"""

    def test_parse_pdf_missing_file(self, client):
        """Test missing file"""
        response = client.post(f'{BASE}/parse-pdf')
        assert response.status_code == 422

    @pytest.mark.skip(reason='PDF parsing tests are temporarily disabled')
    def test_parse_pdf_empty_filename(self, client):
        """Test empty filename"""
        response = client.post(f'{BASE}/parse-pdf', data={'file': (BytesIO(), '')})
        assert response.status_code == 400

    @pytest.mark.skip(reason='PDF parsing tests are temporarily disabled')
    def test_parse_pdf_wrong_extension(self, client):
        """Test non-PDF file"""
        response = client.post(f'{BASE}/parse-pdf', data={
            'file': (BytesIO(b'test'), 'test.txt')
        })
        assert response.status_code == 400
        data = response.json()
        assert 'Only PDF supported' in data['error']

    @pytest.mark.skip(reason='PDF parsing tests are temporarily disabled')
    def test_parse_pdf_success(self, client, mock_parser):
        """Test successful PDF parsing"""
        mock_parser.parse_pdf_chapter.return_value = "# Test Markdown"

        with patch('orchestrate.server.frontend_support_server.PreFlow') as MockPreFlow:
            mock_preflow = MagicMock()
            mock_preflow.model_dump_json.return_value = '{"name": "test"}'
            MockPreFlow.return_value = mock_preflow

            response = client.post(f'{BASE}/parse-pdf', data={
                'file': (BytesIO(b'%PDF-1.4 test'), 'test.pdf')
            })

            # Note: original code returns a dict, not jsonify; testing actual behavior
            assert response.status_code == 200

    @pytest.mark.skip(reason='PDF parsing tests are temporarily disabled')
    def test_parse_pdf_parse_failure(self, client, mock_parser):
        """Test parsing failure"""
        mock_parser.parse_pdf_chapter.return_value = None

        response = client.post(f'{BASE}/parse-pdf', data={
            'file': (BytesIO(b'%PDF-1.4 test'), 'test.pdf')
        })

        assert response.status_code == 400
        data = response.json()
        assert 'Parsing failed' in data['error']


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

    def test_stream_response_format(self, client, mock_retrieval, mock_agent_lib):
        """Test SSE response format"""
        mock_psop = MagicMock()
        mock_psop.id = "123"
        mock_psop.name = "test_workflow"
        mock_psop.steps = []
        mock_retrieval.get_psop_by_id.return_value = mock_psop

        mock_card = MagicMock()
        mock_agent_lib.return_value = [mock_card]

        with patch('orchestrate.server.sse_executor.DynamicWorkflowEngine') as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.set_push_callback = MagicMock()
            mock_engine.run = MagicMock()
            mock_engine.run.return_value = []
            mock_engine.execution_history = []

            response = client.get(f'{BASE}/execute?psop_id=123')

            assert response.status_code == 200
            assert response.headers['content-type'].startswith('text/event-stream')
            assert response.headers['Cache-Control'] == 'no-cache'

import pytest
import json
import os
import atexit
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

_prev_testing = os.environ.get('TESTING')
os.environ['TESTING'] = 'True'

from orchestrate.server.frontend_support_server import app

at_exit_fn = lambda: os.environ.pop('TESTING', None) if _prev_testing is None else os.environ.__setitem__('TESTING', _prev_testing)
atexit.register(at_exit_fn)

client = TestClient(app)
BASE = "/rest/v1/orchestrate"


@pytest.fixture(autouse=True)
def mock_deps():
    fake_save = MagicMock()
    fake_save.handle.return_value = "test-id"
    fake_delete = MagicMock()
    fake_delete.handle.return_value = True

    class FakeRetrieval:
        def list_recent_workflows(self, limit=10, workflow_type='psop'):
            return []
        def get_psop_by_id(self, wid):
            return None
        def retrieve_psop_by_intent(self, intent, limit=5):
            return None
        def retrieve_psop_by_intent_topn(self, intent, top_n=3):
            return []

    fake_retrieval = MagicMock(wraps=FakeRetrieval())

    fake_psop_gen = MagicMock()
    fake_psop_gen.generate.return_value = type("psop", (), {"id": "g-1", "model_dump": lambda: {}})()
    fake_intent_gen = MagicMock()
    fake_intent_gen.generate.return_value = type("psop", (), {"id": "g-2", "model_dump": lambda: {}})()
    fake_parser = MagicMock()
    fake_parser.parse_solution_package.return_value = "parsed text"

    with patch.object(app.state, 'semaphore', False, create=True), \
         patch('orchestrate.server.frontend_support_server.agent_cards_semaphore') as mock_sem, \
         patch('orchestrate.server.shared_handlers.SharedHandlers.save_psop', return_value=fake_save), \
         patch('orchestrate.server.shared_handlers.SharedHandlers.delete_psop', return_value=fake_delete), \
         patch('orchestrate.server.shared_handlers.SharedHandlers.retrieval', return_value=fake_retrieval), \
         patch('orchestrate.server.frontend_support_server.PsopGenerator', return_value=fake_psop_gen), \
         patch('orchestrate.server.frontend_support_server.IntentPsopGenerator', return_value=fake_intent_gen), \
         patch('orchestrate.server.frontend_support_server.SolutionPackageParser', return_value=fake_parser), \
         patch('orchestrate.server.frontend_support_server.get_agent_cards', return_value=[]), \
         patch('orchestrate.server.frontend_support_server.HandlerRegistry', MagicMock()):
        yield


# ──── Workflow ────

def test_get_workflows():
    resp = client.get(f"{BASE}/workflows")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] in ("success", "empty")


def test_create_workflow():
    psop = {"id": "test-001", "name": "Test", "steps": []}
    resp = client.post(f"{BASE}/workflows", json={"psop": psop})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "success"


def test_get_workflow_not_found():
    resp = client.get(f"{BASE}/workflows/nonexistent")
    assert resp.status_code == 404


def test_delete_workflow_not_found():
    resp = client.delete(f"{BASE}/workflows/nonexistent")
    assert resp.status_code == 404


# ──── Agent Cards ────

def test_get_agent_cards():
    resp = client.get(f"{BASE}/agent-cards")
    assert resp.status_code == 200


# ──── Templates ────

def test_get_templates():
    resp = client.get(f"{BASE}/templates")
    assert resp.status_code == 200


def test_import_template_not_found():
    resp = client.post(f"{BASE}/templates/nonexistent-id/import")
    assert resp.status_code == 404


# ──── Execution Records ────

def test_get_execution_records():
    resp = client.get(f"{BASE}/execution-records")
    assert resp.status_code == 200


def test_get_execution_record_not_found():
    resp = client.get(f"{BASE}/execution-records/nonexistent")
    assert resp.status_code in (200, 404)


def test_delete_execution_record_not_found():
    resp = client.delete(f"{BASE}/execution-records/nonexistent")
    assert resp.status_code in (200, 404)


# ──── Legacy Routes ────

def test_legacy_agent_cards():
    resp = client.get("/agent-cards")
    assert resp.status_code == 200


def test_legacy_psops():
    resp = client.get("/psops")
    assert resp.status_code == 200


# ──── Intent Routes ────

def test_retrieve_by_intent_empty():
    resp = client.post(f"{BASE}/retrieve-by-intent", json={"user_intent": "test"})
    assert resp.status_code == 200


def test_generate_from_intent_missing_intent():
    resp = client.post(f"{BASE}/generate-from-intent", json={})
    assert resp.status_code == 422


# ──── TopN Retrieval ────

def test_retrieve_topn_by_intent():
    resp = client.post(f"{BASE}/retrieve-topn-by-intent", json={"user_intent": "test"})
    assert resp.status_code == 200, resp.text
    js = resp.json()
    assert js["status"] == "success"
    assert isinstance(js.get("data"), list)

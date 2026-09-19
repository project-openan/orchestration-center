import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrate.core.model.psop import PSOP, JumpCondition, Step, Task
from orchestrate.sandbox.models import SandboxRunReport, StubScenario, StubTemplate
from orchestrate.sandbox.service import SandboxService
from orchestrate.sandbox.store import SandboxStore
from orchestrate.server import sandbox_api
from orchestrate.validation.sandbox_validator import SandboxCheckStatus


def _psop():
    return PSOP(
        id="wf-1",
        name="sandbox api flow",
        steps=[
            Step(
                name="step_1",
                subtasks=[Task(description="task", agent="agent-a", skill="skill-a")],
                next=[JumpCondition(step="endNode", condition="")],
            )
        ],
    )


class _FakeRetrieval:
    def get_psop_by_id(self, workflow_id):
        if workflow_id == "wf-1":
            return _psop()
        return None


class _FakeStore:
    def __init__(self):
        self.reports = {}
        self.deleted = []

    def load_report(self, verification_id):
        return self.reports.get(verification_id)

    def list_reports(self):
        return []

    def delete_report(self, verification_id):
        if verification_id not in self.reports:
            return False
        del self.reports[verification_id]
        self.deleted.append(verification_id)
        return True

    def save_templates(self, workflow_id, templates):
        return len(templates)

    def load_templates(self, workflow_id):
        return []


class _FakeService:
    def __init__(self):
        self.store = _FakeStore()
        self.started = None

    async def start(self, psop, agent_cards, **kwargs):
        self.started = {
            "workflow_id": psop.id,
            "scenario": kwargs.get("scenario"),
            "templates": kwargs.get("templates"),
        }
        return "verification-1"

    def delete_report(self, verification_id):
        return self.store.delete_report(verification_id)

    def validate_templates(self, payload):
        if not isinstance(payload, list):
            raise ValueError("templates must be a JSON array")
        if any(item.get("response_text") == "bad" for item in payload):
            raise ValueError("Invalid stub template")
        return payload


@pytest.fixture()
def client(monkeypatch):
    fake_service = _FakeService()
    monkeypatch.setattr(sandbox_api, "sandbox_service", fake_service)
    monkeypatch.setattr(
        sandbox_api.SharedHandlers,
        "retrieval",
        lambda: _FakeRetrieval(),
    )
    async def fake_agent_cards():
        return []

    monkeypatch.setattr(sandbox_api, "get_agent_cards", fake_agent_cards)
    app = FastAPI()
    app.include_router(sandbox_api.sandbox_router, prefix="/api/v1/orchestrate")
    yield TestClient(app), fake_service


def test_start_sandbox_uses_separate_api_and_service(client):
    api, service = client
    response = api.post(
        "/api/v1/orchestrate/sandbox/wf-1/run",
        json={"scenario": "error", "templates": [{"response_text": "hello"}]},
    )

    assert response.status_code == 202
    assert response.json()["data"]["verification_id"] == "verification-1"
    assert service.started["workflow_id"] == "wf-1"
    assert service.started["scenario"] == StubScenario.ERROR


def test_start_sandbox_uses_editor_snapshot_without_persistence(client):
    api, service = client
    psop = _psop().model_dump(mode="json")
    psop["id"] = "draft-workflow"

    response = api.post(
        "/api/v1/orchestrate/sandbox/draft-workflow/run",
        json={"scenario": "success", "psop": psop},
    )

    assert response.status_code == 202
    assert response.json()["data"]["verification_id"] == "verification-1"
    assert service.started["workflow_id"] == "draft-workflow"


def test_invalid_template_is_rejected(client):
    api, service = client
    response = api.post(
        "/api/v1/orchestrate/sandbox/wf-1/run",
        json={"templates": [{"response_text": "bad"}]},
    )

    assert response.status_code == 400
    assert service.started is None


def test_get_sandbox_report_and_events(client):
    api, service = client
    service.store.reports["verification-1"] = {
        "status": "completed",
        "report": {"verification_id": "verification-1", "verdict": "pass"},
        "events": [{"type": "start"}],
    }

    report = api.get("/api/v1/orchestrate/sandbox/verifications/verification-1")
    events = api.get("/api/v1/orchestrate/sandbox/verifications/verification-1/events")

    assert report.status_code == 200
    assert report.json()["data"]["report"]["verdict"] == "pass"
    assert events.status_code == 200
    assert events.json()["data"] == [{"type": "start"}]


def test_delete_sandbox_report_endpoint(client):
    api, service = client
    service.store.reports["verification-1"] = {
        "status": "completed",
        "report": {"verification_id": "verification-1", "verdict": "pass"},
        "events": [],
    }

    response = api.delete("/api/v1/orchestrate/sandbox/verifications/verification-1")
    missing = api.delete("/api/v1/orchestrate/sandbox/verifications/verification-1")

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == "verification-1"
    assert service.store.deleted == ["verification-1"]
    assert missing.status_code == 404


def test_save_templates_endpoint(client):
    api, _ = client
    response = api.put(
        "/api/v1/orchestrate/sandbox/templates/wf-1",
        json=[{"response_text": "ok"}],
    )

    assert response.status_code == 200
    assert response.json()["data"]["template_count"] == 1


def test_sandbox_store_persists_reports():
    base = Path("data") / "test-sandbox-store"
    shutil.rmtree(base, ignore_errors=True)
    try:
        store = SandboxStore(base)
        report = SandboxRunReport(
            workflow_id="wf-1",
            workflow_name="flow",
            scenario=StubScenario.SUCCESS,
            verdict=SandboxCheckStatus.PASS,
        )
        store.save_report(report, [{"type": "start"}])

        loaded = store.load_report(report.verification_id)
        assert loaded["status"] == "completed"
        assert loaded["report"]["mode"] == "sandbox"
        assert loaded["events"] == [{"type": "start"}]

        assert store.delete_report(report.verification_id) is True
        assert store.load_report(report.verification_id) is None
        assert store.delete_report(report.verification_id) is False
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.asyncio
async def test_service_uses_polling_id_for_report(monkeypatch, tmp_path):
    captured = {}

    async def fake_run_sandbox(
        psop, agent_cards, control_point, *, verification_id, **kwargs
    ):
        captured["verification_id"] = verification_id
        return SandboxRunReport(
            verification_id=verification_id,
            workflow_id=psop.id,
            workflow_name=psop.name,
            scenario=kwargs.get("scenario", StubScenario.SUCCESS),
            verdict=SandboxCheckStatus.PASS,
        )

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", fake_run_sandbox)
    service = SandboxService(
        control_point_factory=lambda **kwargs: None,
        store=SandboxStore(tmp_path),
    )
    verification_id = await service.start(
        _psop(),
        [],
        templates=[StubTemplate(response_text="ok")],
    )
    await service.wait(verification_id)

    assert captured["verification_id"] == verification_id
    assert service.status(verification_id)["status"] == "completed"
    assert service.store.load_report(verification_id)["report"]["verification_id"] == verification_id
    assert service.delete_report(verification_id) is True
    assert service.status(verification_id) is None
    assert service.events(verification_id) == []

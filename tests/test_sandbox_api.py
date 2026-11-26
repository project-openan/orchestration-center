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

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

    async def cancel_and_delete(self, verification_id, principal=None):
        return self.store.delete_report(verification_id)

    def report(self, verification_id, principal=None):
        return self.store.load_report(verification_id)

    def list_reports(self, principal=None):
        return self.store.list_reports()

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
    @app.middleware("http")
    async def verified_fixture(request, call_next):
        from orchestrate.server.auth import SessionIdentity
        request.state.user_identity = SessionIdentity("fixture-admin", "admin")
        return await call_next(request)
    app.include_router(sandbox_api.sandbox_router, prefix="/rest/v1/orchestrate")
    yield TestClient(app), fake_service


def test_start_sandbox_uses_separate_api_and_service(client):
    api, service = client
    response = api.post(
        "/rest/v1/orchestrate/sandbox/wf-1/run",
        json={"scenario": "error", "templates": [{"response_text": "hello"}]},
    )

    assert response.status_code == 202
    assert response.json()["data"]["verification_id"] == "verification-1"
    assert response.json()["data"]["status"] == "queued"
    assert service.started["workflow_id"] == "wf-1"
    assert service.started["scenario"] == StubScenario.ERROR


def test_sandbox_routes_are_not_exposed_by_external_api():
    from orchestrate.server.external_api import router as external_router

    assert not any("/sandbox" in route.path for route in external_router.routes)


def test_start_sandbox_uses_editor_snapshot_without_persistence(client):
    api, service = client
    psop = _psop().model_dump(mode="json")
    psop["id"] = "draft-workflow"

    response = api.post(
        "/rest/v1/orchestrate/sandbox/draft-workflow/run",
        json={"scenario": "success", "psop": psop},
    )

    assert response.status_code == 202
    assert response.json()["data"]["verification_id"] == "verification-1"
    assert service.started["workflow_id"] == "draft-workflow"


def test_invalid_template_is_rejected(client):
    api, service = client
    response = api.post(
        "/rest/v1/orchestrate/sandbox/wf-1/run",
        json={"templates": [{"response_text": "bad"}]},
    )

    assert response.status_code == 400
    assert service.started is None


@pytest.mark.parametrize("editor_snapshot", [True, False])
def test_role_sandbox_rejects_before_registry_or_queue(client, monkeypatch, editor_snapshot):
    api, service = client
    payload = _psop().model_dump(mode="json")
    payload["catalog_version"] = "synthetic-v1"
    payload["steps"][0]["subtasks"][0].update(binding="role", role_version="1")
    role_psop = PSOP.model_validate(payload)
    monkeypatch.setattr(sandbox_api.SharedHandlers, "retrieval", lambda: SimpleNamespace(
        get_psop_by_id=lambda _: role_psop))
    registry = AsyncMock(return_value=[])
    monkeypatch.setattr(sandbox_api, "get_agent_cards", registry)
    response = api.post("/rest/v1/orchestrate/sandbox/wf-1/run",
                        json={"psop": payload} if editor_snapshot else {})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ROLE_SANDBOX_NOT_SUPPORTED"
    registry.assert_not_awaited()
    assert service.started is None


def test_get_sandbox_report_and_events(client):
    api, service = client
    service.store.reports["verification-1"] = {
        "status": "completed",
        "report": {"verification_id": "verification-1", "verdict": "pass"},
        "events": [{"type": "start"}],
    }

    report = api.get("/rest/v1/orchestrate/sandbox/verifications/verification-1")
    events = api.get("/rest/v1/orchestrate/sandbox/verifications/verification-1/events")

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

    response = api.delete("/rest/v1/orchestrate/sandbox/verifications/verification-1")
    missing = api.delete("/rest/v1/orchestrate/sandbox/verifications/verification-1")

    assert response.status_code == 200
    assert response.json()["data"]["deleted"] == "verification-1"
    assert service.store.deleted == ["verification-1"]
    assert missing.status_code == 404


def test_save_templates_endpoint(client):
    api, _ = client
    response = api.put(
        "/rest/v1/orchestrate/sandbox/templates/wf-1",
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


def test_sandbox_store_bounds_persisted_report(tmp_path):
    store = SandboxStore(tmp_path, max_report_bytes=1500)
    report = SandboxRunReport(
        workflow_id="wf-1",
        workflow_name="flow",
        scenario=StubScenario.SUCCESS,
        verdict=SandboxCheckStatus.PASS,
        risks=["large-risk" * 1000],
    )

    store.save_report(report, [{"type": "start", "data": "large-event" * 1000}])
    stored = store.load_report(report.verification_id)
    assert (store.report_dir / f"{report.verification_id}.json").stat().st_size <= 1500
    assert stored["report"]["verdict"] == "pass"
    assert stored["report"]["report_truncated"] is True
    assert stored["report"]["events_truncated"] is True
    assert stored["events"] == []


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


@pytest.mark.asyncio
async def test_control_point_transport_defaults_follow_server_defaults(monkeypatch, tmp_path):
    # 键缺省时,沙箱推导的传输参数必须与主服务的默认一致(https + 服务端校验),
    # 否则省略配置的部署会出现沙箱走 http、主服务在 https 的静默失配
    captured = {}

    async def fake_run_sandbox(psop, agent_cards, control_point, *, verification_id, **kwargs):
        return SandboxRunReport(
            verification_id=verification_id,
            workflow_id=psop.id,
            workflow_name=psop.name,
            scenario=StubScenario.SUCCESS,
            verdict=SandboxCheckStatus.PASS,
        )

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", fake_run_sandbox)
    monkeypatch.setattr("orchestrate.sandbox.service.get_conf", lambda: {})
    service = SandboxService(
        control_point_factory=lambda **kwargs: captured.update(kwargs) or None,
        store=SandboxStore(tmp_path),
    )
    verification_id = await service.start(_psop(), [])
    await service.wait(verification_id)

    assert captured["orch_url"] == "https://127.0.0.1:5001"
    assert captured["ssl_verify"] is True


@pytest.mark.asyncio
async def test_service_limits_concurrent_runs(monkeypatch, tmp_path):
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    starts = 0

    async def fake_run_sandbox(
        psop, agent_cards, control_point, *, verification_id, **kwargs
    ):
        nonlocal starts
        starts += 1
        if starts == 1:
            first_started.set()
            await release_first.wait()
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
        max_concurrent_runs=1,
    )

    first_id = await service.start(_psop(), [])
    await first_started.wait()
    second_id = await service.start(_psop(), [])
    await asyncio.sleep(0)

    assert service.status(first_id)["status"] == "running"
    assert service.status(second_id)["status"] == "queued"
    assert starts == 1

    release_first.set()
    await service.wait(first_id)
    await service.wait(second_id)
    assert starts == 2


@pytest.mark.asyncio
async def test_delete_cancels_a_running_verification(monkeypatch, tmp_path):
    started = asyncio.Event()

    async def fake_run_sandbox(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", fake_run_sandbox)
    service = SandboxService(
        control_point_factory=lambda **kwargs: None,
        store=SandboxStore(tmp_path),
    )
    verification_id = await service.start(_psop(), [])
    await started.wait()

    assert await service.cancel_and_delete(verification_id) is True
    assert service.status(verification_id) is None
    assert service.store.load_report(verification_id) is None
    assert await service.cancel_and_delete(verification_id) is False


@pytest.mark.asyncio
async def test_service_times_out_a_long_running_verification(monkeypatch, tmp_path):
    async def fake_run_sandbox(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr("orchestrate.sandbox.service.run_sandbox", fake_run_sandbox)
    service = SandboxService(
        control_point_factory=lambda **kwargs: None,
        store=SandboxStore(tmp_path),
        run_timeout_seconds=0.01,
    )
    verification_id = await service.start(_psop(), [])
    await service.wait(verification_id)

    stored = service.store.load_report(verification_id)
    assert service.status(verification_id)["status"] == "timed_out"
    assert stored["status"] == "timed_out"
    assert "exceeded" in stored["report"]["error"]

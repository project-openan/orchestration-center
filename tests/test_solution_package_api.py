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
"""Route tests for the imported solution package endpoints.

The routes read/write through SolutionPackageManager, so the tests point the
manager at a temporary storage directory instead of the real data directory.

Business tests opt into a synthetic authenticated session, not an auth bypass.
"""
import pytest
from fastapi.testclient import TestClient

from orchestrate.server import frontend_support_server


@pytest.fixture()
def client(tmp_path, monkeypatch, account_session):
    monkeypatch.setattr(
        frontend_support_server.solution_package_manager,
        "storage_dir", tmp_path / "solution_packages",
    )
    frontend_support_server.solution_package_manager.storage_dir.mkdir(
        parents=True, exist_ok=True
    )
    with TestClient(frontend_support_server.app, headers=account_session) as tc:
        yield tc


def _store(package_manager, filename, chapters):
    assert package_manager.store_solution_package(filename, chapters)


def test_list_returns_stored_packages(client):
    _store(frontend_support_server.solution_package_manager,
           "demo.pdf", {"1. Overview": "content one", "2. Steps": "content two"})
    resp = client.get("/rest/v1/orchestrate/solution-packages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    names = [p["pdf_filename"] for p in body["data"]]
    assert names == ["demo.pdf"]


def test_get_returns_full_package(client):
    manager = frontend_support_server.solution_package_manager
    _store(manager, "demo.pdf", {"1. Overview": "content one"})
    resp = client.get("/rest/v1/orchestrate/solution-packages/demo.pdf")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pdf_filename"] == "demo.pdf"
    assert data["chapters"]["1. Overview"] == "content one"


def test_get_unknown_package_returns_404(client):
    resp = client.get("/rest/v1/orchestrate/solution-packages/missing.pdf")
    assert resp.status_code == 404


def test_delete_removes_stored_package(client):
    manager = frontend_support_server.solution_package_manager
    _store(manager, "demo.pdf", {"1. Overview": "content one"})
    resp = client.delete("/rest/v1/orchestrate/solution-packages/demo.pdf")
    assert resp.status_code == 200
    assert not (manager.storage_dir / "demo.pdf").exists()
    resp = client.get("/rest/v1/orchestrate/solution-packages/demo.pdf")
    assert resp.status_code == 404


def test_delete_unknown_package_returns_404(client):
    resp = client.delete("/rest/v1/orchestrate/solution-packages/missing.pdf")
    assert resp.status_code == 404


def _pdf(title='6. Interaction Flow'):
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), 'INTRO_MARKER')
    doc.new_page().insert_text((72, 72), 'FINAL_FLOW_MARKER')
    doc.set_toc([[1, '1. Introduction', 1], [1, title, 2]])
    content = doc.tobytes()
    doc.close()
    return content


@pytest.fixture
def synthetic_llm(monkeypatch):
    from unittest.mock import MagicMock
    llm = MagicMock()
    llm.ask_llm.return_value = ('', '# Synthetic steps\n1. Analyze')
    monkeypatch.setattr('orchestrate.solution_package.parse_flow.get_llm_instance', lambda: llm)
    return llm


@pytest.mark.parametrize('title', ['5. Interaction Flow', '6. Interaction Flow'])
def test_upload_accepts_flow_number_and_last_page(client, synthetic_llm, title):
    response = client.post('/rest/v1/orchestrate/parse-pdf', files={'file': ('flow.pdf', _pdf(title), 'application/pdf')})
    assert response.status_code == 200
    assert response.json()['data']['steps_md'] == '# Synthetic steps\n1. Analyze'
    prompts = [call.args[0] for call in synthetic_llm.ask_llm.call_args_list]
    assert any('FINAL_FLOW_MARKER' in prompt for prompt in prompts)
    package = frontend_support_server.solution_package_manager.retrieve_by_filename('flow.pdf')
    assert title in package['chapters']


def test_missing_flow_does_not_persist_a_partially_successful_import(client, synthetic_llm):
    response = client.post('/rest/v1/orchestrate/parse-pdf', files={'file': ('missing.pdf', _pdf('2. Summary'), 'application/pdf')})
    assert response.status_code == 400
    assert frontend_support_server.solution_package_manager.retrieve_by_filename('missing.pdf') is None


def test_failed_model_conversion_is_not_saved_as_markdown(client, synthetic_llm):
    synthetic_llm.ask_llm.side_effect = RuntimeError('synthetic model error')
    response = client.post('/rest/v1/orchestrate/parse-pdf', files={'file': ('failed.pdf', _pdf(), 'application/pdf')})
    assert response.status_code == 500
    assert frontend_support_server.solution_package_manager.retrieve_by_filename('failed.pdf') is None


def test_failed_package_write_is_not_reported_as_success(client, synthetic_llm, monkeypatch):
    monkeypatch.setattr(frontend_support_server.solution_package_manager, 'store_solution_package', lambda *_: False)
    response = client.post('/rest/v1/orchestrate/parse-pdf', files={'file': ('write.pdf', _pdf(), 'application/pdf')})
    assert response.status_code == 503

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

TESTING is set before the app import so the auth middleware treats every
request as authenticated regardless of the local server.conf (mirrors
test_frontend_support_server.py).
"""
import atexit
import os

_prev_testing = os.environ.get('TESTING')
os.environ['TESTING'] = 'True'

import pytest
from fastapi.testclient import TestClient

from orchestrate.server import frontend_support_server


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        frontend_support_server.solution_package_manager,
        "storage_dir", tmp_path / "solution_packages",
    )
    frontend_support_server.solution_package_manager.storage_dir.mkdir(
        parents=True, exist_ok=True
    )
    with TestClient(frontend_support_server.app) as tc:
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

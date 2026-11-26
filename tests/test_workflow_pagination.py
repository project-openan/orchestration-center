# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.retrieval import WorkflowRetrieval
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.persistence import StorageContext
from orchestrate.persistence.file_backend import FilePersistenceBackend
from orchestrate.server.frontend_support_server import app


def test_workflow_pages_are_complete_and_stable_at_equal_timestamps(tmp_path, monkeypatch, account_session):
    storage = WorkflowStorage(str(tmp_path/'workflows'))
    context = StorageContext(FilePersistenceBackend(storage=storage))
    for index in range(105):
        context.psops.save(PSOP(id=f'workflow-{index:03}', name='Synthetic', steps=[],
                                created_at=datetime(2026, 10, 19, tzinfo=timezone.utc)))
    monkeypatch.setattr(SharedHandlers, '_retrieval', WorkflowRetrieval(storage, context=context))
    client = TestClient(app, headers=account_session)
    first = client.get('/rest/v1/orchestrate/workflows?limit=100').json()
    assert len(first['data']) == 100
    assert first['pagination'] == {'offset': 0, 'limit': 100, 'has_more': True}
    second = client.get('/rest/v1/orchestrate/workflows?limit=100&offset=100').json()
    assert len(second['data']) == 5
    assert second['pagination']['has_more'] is False
    ids = [item['workflow_id'] for item in first['data'] + second['data']]
    assert len(set(ids)) == 105
    assert ids == sorted(ids, reverse=True)
    assert len(client.get('/rest/v1/orchestrate/workflows').json()['data']) == 10
    assert client.get('/rest/v1/orchestrate/workflows?offset=-1').status_code == 422

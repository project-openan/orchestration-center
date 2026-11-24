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
"""Coverage for file-mode storage handler adapters over WorkflowStorage."""

from unittest.mock import MagicMock

from orchestrate.core.model.execution_record import ExecutionRecord
from orchestrate.core.model.psop import PSOP
from orchestrate.handlers import file_handlers


def _patch_storage(monkeypatch, storage):
    monkeypatch.setattr(file_handlers, "get_workflow_storage", lambda: storage)
    return storage


def test_get_all_psops_handler_builds_search_results(monkeypatch, sample_psop_dict):
    storage = MagicMock()
    psop = PSOP.model_validate(sample_psop_dict)
    storage.list_psops.return_value = [psop.id]
    storage.load_psop.return_value = psop
    _patch_storage(monkeypatch, storage)

    results = file_handlers.GetAllPsopsHandler().handle()

    assert len(results) == 1
    assert results[0].workflow_id == psop.id
    assert results[0].workflow_type == "psop"
    assert results[0].name == psop.name


def test_get_all_psops_handler_skips_missing_psops(monkeypatch, sample_psop_dict):
    storage = MagicMock()
    psop = PSOP.model_validate(sample_psop_dict)
    storage.list_psops.return_value = [psop.id, "ghost"]
    storage.load_psop.side_effect = [psop, None]
    _patch_storage(monkeypatch, storage)

    results = file_handlers.GetAllPsopsHandler().handle()
    assert [r.workflow_id for r in results] == [psop.id]


def test_save_psop_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.save_psop.return_value = "wf-1"
    _patch_storage(monkeypatch, storage)
    assert file_handlers.SavePsopHandler().handle("payload") == "wf-1"
    storage.save_psop.assert_called_once_with("payload")


def test_get_psop_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.load_psop.return_value = "psop-obj"
    _patch_storage(monkeypatch, storage)
    assert file_handlers.GetPsopHandler().handle("wf-1") == "psop-obj"
    storage.load_psop.assert_called_once_with("wf-1")


def test_delete_psop_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.delete_psop.return_value = True
    _patch_storage(monkeypatch, storage)
    assert file_handlers.DeletePsopHandler().handle("wf-1") is True
    storage.delete_psop.assert_called_once_with("wf-1")


def test_save_execution_record_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.save_execution_record.return_value = "ex-1"
    _patch_storage(monkeypatch, storage)
    assert file_handlers.SaveExecutionRecordHandler().handle("rec") == "ex-1"


def test_list_execution_records_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.list_execution_records.return_value = [{"id": "ex-1"}]
    _patch_storage(monkeypatch, storage)
    assert file_handlers.ListExecutionRecordsHandler().handle() == [{"id": "ex-1"}]


def test_get_execution_record_handler_delegates(monkeypatch):
    record = ExecutionRecord(psop_id="wf-1")
    storage = MagicMock()
    storage.load_execution_record.return_value = record
    _patch_storage(monkeypatch, storage)
    assert file_handlers.GetExecutionRecordHandler().handle(record.execution_id) is record


def test_delete_execution_record_handler_delegates(monkeypatch):
    storage = MagicMock()
    storage.delete_execution_record.return_value = True
    _patch_storage(monkeypatch, storage)
    assert file_handlers.DeleteExecutionRecordHandler().handle("ex-1") is True

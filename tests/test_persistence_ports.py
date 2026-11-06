# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the storage ports, the storage context and the factory.

These tests are the guard rails for the ports themselves, not for one backend's
behaviour: they pin the shape of the contracts (split per repository, declared
capabilities, no copied mode list) and the fact that importing the file backend
never drags in a database driver.
"""

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from common.util import persistence_mode
from orchestrate.core.model.execution_record import ExecutionRecord
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.task_summary import build_tasks_summary
from orchestrate.persistence import (
    Capability,
    ExecutionRecordRepository,
    PersistenceBackend,
    PreflowRepository,
    PsopRepository,
    StorageConfigError,
    StorageConflictError,
    StorageContext,
    StorageCorruptionError,
    StorageError,
    StorageUnavailableError,
    StorageValidationError,
    UserRepository,
    configure_context,
    create_backend,
    current_context,
    known_modes,
)
from orchestrate.persistence import factory
from orchestrate.persistence.file_backend import FilePersistenceBackend
from orchestrate.persistence.sql_backend import SqlPersistenceBackend

REPO_ROOT = Path(__file__).resolve().parents[1]

# Importing the file backend must not import a database driver. Checked in a
# fresh interpreter: another test module may already have imported one.
_DRIVER_FREE_PROBE = (
    "import sys\n"
    "from orchestrate.persistence import build_context\n"
    "context = build_context('file')\n"
    "assert context.mode == 'file'\n"
    "print('DRIVERS', 'psycopg2' in sys.modules, 'pymysql' in sys.modules)\n"
)


def _file_context(tmp_path):
    return StorageContext(FilePersistenceBackend(storage=WorkflowStorage(str(tmp_path))))


def _sql_context(tmp_path, mode="postgresql"):
    return StorageContext(SqlPersistenceBackend(mode=mode, storage=WorkflowStorage(str(tmp_path))))


def test_known_modes_is_the_existing_single_source_of_truth():
    # Identity, not equality: a copied list would pass == and still be a second
    # enumeration to keep in sync every time a backend is added.
    assert known_modes() is persistence_mode.KNOWN_STORAGE_MODES


def test_create_rejects_an_unknown_mode_instead_of_falling_back_to_file():
    with pytest.raises(StorageConfigError) as error:
        create_backend("sqlite")
    assert "sqlite" in str(error.value)


def test_create_reports_a_known_mode_without_a_registered_builder(monkeypatch):
    monkeypatch.delitem(factory._BUILDERS, "mysql")
    with pytest.raises(StorageConfigError) as error:
        create_backend("mysql")
    assert "mysql" in str(error.value)


def test_create_reads_the_configured_mode_and_normalizes_case(monkeypatch):
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "file"})
    assert create_backend().mode == "file"
    assert create_backend("MYSQL").mode == "mysql"


def test_ports_are_split_per_repository_and_stay_abstract():
    for port in (PsopRepository, ExecutionRecordRepository, PreflowRepository,
                 UserRepository, PersistenceBackend):
        assert inspect.isabstract(port), f"{port.__name__} must stay abstract"
    # Split interfaces are the point: a backend implements exactly what it has,
    # instead of inheriting a fat contract with two dozen abstract methods.
    assert set(PsopRepository.__abstractmethods__) == {"save", "get", "list_summaries", "delete"}
    assert set(ExecutionRecordRepository.__abstractmethods__) == {"save", "get", "list_summaries", "delete"}
    assert set(PreflowRepository.__abstractmethods__) == {"save", "get", "list_ids", "delete"}
    assert set(PersistenceBackend.__abstractmethods__) == {
        "check_ready", "initialize", "psops", "executions", "preflows", "psops_for", "close",
    }


def test_storage_error_hierarchy_keeps_the_failure_modes_apart():
    assert issubclass(StorageConfigError, StorageValidationError)
    assert issubclass(StorageValidationError, StorageError)
    # "unreachable" must not be catchable as "you passed a bad value", and a
    # conflict is not corruption: each maps to a different HTTP answer.
    assert not issubclass(StorageUnavailableError, StorageValidationError)
    assert not issubclass(StorageConflictError, StorageCorruptionError)
    assert issubclass(StorageUnavailableError, StorageError)
    assert issubclass(StorageCorruptionError, StorageError)
    assert issubclass(StorageConflictError, StorageError)


def test_context_requires_a_backend_that_declares_its_mode(tmp_path):
    backend = FilePersistenceBackend(storage=WorkflowStorage(str(tmp_path)))
    backend.mode = ""
    with pytest.raises(ValueError):
        StorageContext(backend)


def test_file_context_declares_no_user_store(tmp_path):
    context = _file_context(tmp_path)
    assert context.mode == "file"
    assert context.has_users is False
    assert context.supports(Capability.USERS) is False
    with pytest.raises(StorageValidationError):
        context.users


def test_file_context_round_trips_psops_through_the_port(tmp_path, sample_psop_dict):
    context = _file_context(tmp_path)
    psop = PSOP.model_validate(sample_psop_dict)
    assert context.psops.save(psop) == psop.id
    assert context.psops.get(psop.id).name == psop.name
    summaries = context.psops.list_summaries()
    assert [summary.workflow_id for summary in summaries] == [psop.id]
    assert summaries[0].tasks_summary == build_tasks_summary(psop)
    assert context.psops.delete(psop.id) is True
    assert context.psops.get(psop.id) is None
    assert context.psops.delete(psop.id) is False


def test_file_context_round_trips_execution_records(tmp_path):
    context = _file_context(tmp_path)
    record = ExecutionRecord(psop_id="psop-1", psop_name="示例🚀")
    assert context.executions.save(record) == record.execution_id
    assert context.executions.get(record.execution_id).psop_name == "示例🚀"
    summaries = context.executions.list_summaries()
    assert [summary["execution_id"] for summary in summaries] == [record.execution_id]
    assert context.executions.delete(record.execution_id) is True
    assert context.executions.get(record.execution_id) is None


def test_sql_backend_composes_a_database_preflow_port(tmp_path):
    from orchestrate.persistence.document_models import DocumentPreflowRepository
    context = _sql_context(tmp_path)
    assert isinstance(context.preflows, PreflowRepository)
    assert isinstance(context.preflows, DocumentPreflowRepository)
    assert context.preflows.documents is context.documents


def test_sql_backend_delegates_to_the_current_processors_and_user_store(monkeypatch, tmp_path, sample_psop_dict):
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "mysql"})
    from database.utils import user_store
    from orchestrate.handlers import psop_processor as psops

    context = _sql_context(tmp_path, mode="mysql")
    assert context.mode == "mysql" and context.has_users is True

    seen = {}
    monkeypatch.setattr(psops, "custom_save_psop", lambda psop: seen.setdefault("saved", psop.id))
    monkeypatch.setattr(psops, "get_psop_by_id", lambda psop_id: seen.setdefault("got", psop_id))
    monkeypatch.setattr(psops, "get_all_psops", lambda: seen.setdefault("listed", []))
    monkeypatch.setattr(psops, "custom_delete_psop", lambda psop_id: seen.setdefault("deleted", psop_id) is not None)
    monkeypatch.setattr(user_store, "has_any_user", lambda: seen.setdefault("has_any", True))

    psop = PSOP.model_validate(sample_psop_dict)
    assert context.psops.save(psop) == psop.id
    assert context.psops.get(psop.id) == psop.id
    assert context.psops.list_summaries() == []
    assert context.psops.delete(psop.id) is True
    assert context.users.has_any() is True
    assert seen == {"saved": psop.id, "got": psop.id, "listed": [], "deleted": psop.id, "has_any": True}


def test_file_mode_does_not_import_a_database_driver():
    completed = subprocess.run(
        [sys.executable, "-c", _DRIVER_FREE_PROBE],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert "DRIVERS False False" in completed.stdout, completed.stdout


def test_psops_for_binds_the_caller_owned_storage(tmp_path, sample_psop_dict):
    # WorkflowRetrieval owns a storage of its own (injected in 25 tests). Its
    # PSOPs must come from that storage, not from the process-wide singleton,
    # which is why the port takes the storage instead of the caller branching
    # on the mode.
    owned = WorkflowStorage(str(tmp_path / "owned"))
    context = StorageContext(FilePersistenceBackend(storage=WorkflowStorage(str(tmp_path / "other"))))
    psop = PSOP.model_validate(sample_psop_dict)
    owned.save_psop(psop)

    repository = context.psops_for(owned)

    assert [summary.workflow_id for summary in repository.list_summaries()] == [psop.id]
    assert repository.get(psop.id).name == psop.name


def test_sql_psops_for_ignores_the_storage_argument(tmp_path):
    context = _sql_context(tmp_path)
    assert isinstance(context.psops_for(WorkflowStorage(str(tmp_path / "elsewhere"))), PsopRepository)


def test_current_context_defaults_to_file_and_can_be_configured(tmp_path, monkeypatch):
    import orchestrate.persistence.context as context_module

    monkeypatch.setattr(context_module, "_persistence_context", None)
    # The app is a module-level FastAPI global that tests import directly, so an
    # unconfigured process must still behave like the historical file default.
    assert current_context().mode == "file"

    configured = StorageContext(FilePersistenceBackend(storage=WorkflowStorage(str(tmp_path))))
    assert configure_context(configured) is configured
    assert current_context() is configured

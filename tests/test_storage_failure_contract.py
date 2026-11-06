# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behavior regressions for the merged-storage review, without network probes."""

from unittest.mock import MagicMock, patch

import pytest
import psycopg2
import pymysql
from fastapi.testclient import TestClient

from common.custom import HandlerRegistry, InterfaceType
from common.util import persistence_mode
from database.utils import db_connection, user_store
from orchestrate.handlers import db_handlers, psop_processor, execution_record_processor
from orchestrate.persistence import create_backend, StorageContext
from orchestrate.persistence.errors import (
    StorageConfigError, StorageConflictError, StorageCorruptionError, StorageError,
    StorageUnavailableError, StorageValidationError,
)


@pytest.fixture
def sql_mode(monkeypatch):
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "mysql"})


def test_inherited_extension_and_same_class_reregistration(monkeypatch, sql_mode):
    class Derived(db_handlers.CustomGetAllPsopsHandler):
        def handle(self):
            return ["extension"]

    monkeypatch.setattr(HandlerRegistry, "_overrides", dict(HandlerRegistry._overrides))
    monkeypatch.setattr(HandlerRegistry, "_bundled_overrides", dict(
        getattr(HandlerRegistry, "_bundled_overrides", {})), raising=False)
    HandlerRegistry.register(InterfaceType.GET_ALL_PSOP, Derived)
    assert create_backend("mysql").psops().list_summaries() == ["extension"]
    HandlerRegistry.register(InterfaceType.GET_ALL_PSOP, Derived, bundled=True)
    assert HandlerRegistry.get_extension_override(InterfaceType.GET_ALL_PSOP) is None
    HandlerRegistry.register(InterfaceType.GET_ALL_PSOP, Derived)
    assert HandlerRegistry.get_extension_override(InterfaceType.GET_ALL_PSOP) is Derived


def test_factory_honors_injected_config_and_explicit_mode(monkeypatch):
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "file"})
    assert create_backend(conf={"persistence_mode": "mysql"}).mode == "mysql"
    assert create_backend("postgresql", conf={"persistence_mode": "mysql"}).mode == "postgresql"


OPERATIONS = [
    lambda b: b.psops().save(MagicMock()), lambda b: b.psops().get("id"),
    lambda b: b.psops().list_summaries(), lambda b: b.psops().delete("id"),
    lambda b: b.executions().save(MagicMock()), lambda b: b.executions().get("id"),
    lambda b: b.executions().list_summaries(), lambda b: b.executions().delete("id"),
    lambda b: b.users().has_any(), lambda b: b.users().authenticate("u", "p"),
    lambda b: b.users().create("u", "p", "user", False), lambda b: b.users().list_accounts(),
    lambda b: b.users().delete("u"), lambda b: b.users().update_password("u", "p"),
    lambda b: b.check_ready(), lambda b: b.initialize(), lambda b: b.close(),
]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_every_sql_operation_uses_bound_provider_despite_global_mode(operation, monkeypatch):
    from database.utils.connection_provider import current_provider
    from database.utils import table_creation
    backend = create_backend("mysql")
    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "postgresql"})
    seen = []
    def probe(*args, **kwargs):
        assert current_provider() is backend._provider
        assert persistence_mode.persistence_mode() == "mysql"
        seen.append(True)
        return MagicMock()
    for module, names in (
        (psop_processor, ("custom_save_psop", "get_psop_by_id", "get_all_psops", "custom_delete_psop")),
        (execution_record_processor, ("db_save_execution_record", "db_get_execution_record",
                                     "db_list_execution_records", "db_delete_execution_record")),
        (user_store, ("has_any_user", "authenticate_user", "create_user", "list_users", "delete_user", "update_password")),
        (db_connection, ("create_connection",)), (table_creation, ("create_tables",))):
        for name in names:
            monkeypatch.setattr(module, name, probe)
    from orchestrate.server import sql_sessions
    monkeypatch.setattr(backend.documents(), "initialize", probe)
    monkeypatch.setattr(sql_sessions, "ensure_auth_schema", probe)
    operation(backend)
    assert current_provider() is None
    assert seen or backend._provider._closed


def test_readiness_uses_one_connection_and_closes_it(sql_mode):
    conn = MagicMock()
    with patch.object(db_connection, "create_connection", side_effect=[conn, None]) as connection:
        create_backend("mysql").check_ready()
    connection.assert_called_once()
    conn.close.assert_called_once()


def test_readiness_none_is_an_outage(sql_mode):
    with patch.object(db_connection, "create_connection", return_value=None):
        with pytest.raises(StorageUnavailableError):
            create_backend("mysql").check_ready()


@pytest.mark.parametrize("module,operation", [
    (psop_processor, lambda: psop_processor.custom_save_psop(MagicMock())),
    (psop_processor, lambda: psop_processor.get_all_psops()),
    (psop_processor, lambda: psop_processor.get_psop_by_id("id")),
    (psop_processor, lambda: psop_processor.custom_delete_psop("id")),
    (execution_record_processor, lambda: execution_record_processor.db_save_execution_record(MagicMock())),
    (execution_record_processor, lambda: execution_record_processor.db_list_execution_records()),
    (execution_record_processor, lambda: execution_record_processor.db_get_execution_record("id")),
    (execution_record_processor, lambda: execution_record_processor.db_delete_execution_record("id")),
    (user_store, lambda: user_store.authenticate_user("u", "p")),
    (user_store, lambda: user_store.list_users()),
    (user_store, lambda: user_store.create_user("u", "p")),
    (user_store, lambda: user_store.user_exists("u")),
    (user_store, lambda: user_store.delete_user("u")),
    (user_store, lambda: user_store.update_password("u", "p")),
])
def test_no_connection_never_masquerades_as_no_data(module, operation):
    with patch.object(module, "create_connection", return_value=None):
        with pytest.raises(StorageUnavailableError):
            operation()


@pytest.mark.parametrize("failure,expected", [
    (TimeoutError("password=not-for-public-output"), StorageUnavailableError),
    (pymysql.err.OperationalError(2013, "connection lost"), StorageUnavailableError),
    (psycopg2.errors.QueryCanceled("query timed out"), StorageUnavailableError),
    (psycopg2.errors.SyntaxError("bad SQL"), StorageError),
])
def test_query_failures_are_classified_and_not_empty(failure, expected):
    with patch.object(psop_processor, "create_connection", return_value=MagicMock()), \
         patch.object(psop_processor, "execute_query", return_value=(None, failure)):
        with pytest.raises(expected) as result:
            psop_processor.get_all_psops()
        assert "password=" not in str(result.value)


def test_bad_document_is_corruption_not_missing():
    with patch.object(psop_processor, "create_connection", return_value=MagicMock()), \
         patch.object(psop_processor, "execute_query", return_value=([(b"not-json",)], None)):
        with pytest.raises(StorageCorruptionError):
            psop_processor.get_psop_by_id("id")


@pytest.mark.parametrize("path", [
    "/rest/v1/orchestrate/workflows", "/rest/v1/orchestrate/workflows/absent",
    "/rest/v1/orchestrate/execution-records", "/api/v1/orchestrate/psop/absent",
    "/api/v1/executions", "/api/v1/executions/absent",
])
def test_routes_return_503_on_outage(path, monkeypatch, sql_mode, account_session):
    from orchestrate.core.shared_handlers import SharedHandlers
    from orchestrate.server import frontend_support_server as server, auth
    from orchestrate.persistence import context

    monkeypatch.setattr(context, "_persistence_context", StorageContext(create_backend("mysql")))
    monkeypatch.setattr(SharedHandlers, "_retrieval", None)
    with patch.object(psop_processor, "create_connection", return_value=None), \
         patch.object(execution_record_processor, "create_connection", return_value=None):
        response = TestClient(server.app, headers=account_session).get(path)
    assert response.status_code == 503, response.text
    assert "password=" not in response.text


def test_cached_user_presence_does_not_turn_login_outage_into_bad_password(monkeypatch, sql_mode):
    from orchestrate.server import frontend_support_server as server, auth
    from orchestrate.persistence import context

    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setattr(context, "_persistence_context", StorageContext(create_backend("mysql")))
    monkeypatch.setattr(user_store, "_any_user_exists_cache", True)
    context._persistence_context.backend._provider.users_observed = True
    from orchestrate.server import middleware
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    monkeypatch.setattr(middleware, "limiter", MovingWindowRateLimiter(MemoryStorage()))
    def unavailable():
        raise ConnectionError("Synthetic authentication storage outage")
    monkeypatch.setattr(context._persistence_context.backend._provider, "connection", unavailable)
    with patch.object(user_store, "create_connection", return_value=None):
        response = TestClient(server.app).post("/rest/v1/orchestrate/auth/login", json={
            "username": "admin", "password": "not-a-real-password",
        })
    assert auth.is_auth_enabled() is True
    assert response.status_code == 503


@pytest.mark.parametrize("failure,code", [
    (StorageUnavailableError("private driver detail"), 503),
    (StorageConflictError("private driver detail"), 409),
    (StorageValidationError("private driver detail"), 422),
    (StorageConfigError("private driver detail"), 500),
    (StorageCorruptionError("private driver detail"), 500),
])
def test_public_storage_mapping_is_stable_and_sanitized(failure, code):
    from orchestrate.server.storage_error_response import storage_http_exception
    mapped = storage_http_exception(failure)
    assert mapped.status_code == code
    assert "private" not in mapped.detail


def test_duplicate_user_is_conflict_not_outage():
    with patch.object(user_store, "create_connection", return_value=MagicMock()), \
         patch.object(user_store, "execute_query", return_value=(None, pymysql.err.IntegrityError(1062, "duplicate"))):
        assert user_store.create_user("u", "p") is False


def test_cursor_acquisition_and_cleanup_preserve_original_failure():
    from database.utils.query_execution import execute_query
    conn = MagicMock()
    failure = ConnectionError("lost")
    conn.cursor.side_effect = failure
    assert execute_query(conn, "SELECT 1") == (None, failure)
    conn.cursor.side_effect = None
    conn.cursor.return_value.execute.side_effect = failure
    conn.cursor.return_value.close.side_effect = RuntimeError("cleanup")
    assert execute_query(conn, "SELECT 1") == (None, failure)


def test_extension_queries_work_through_actual_retrieval(monkeypatch, sql_mode, tmp_path, sample_psop_dict):
    from orchestrate.core.model.psop import PSOP
    from orchestrate.core.persistence import WorkflowStorage
    from orchestrate.core.retrieval import WorkflowRetrieval
    from orchestrate.core.workflow_search_result import WorkflowSearchResult

    psop = PSOP.model_validate(sample_psop_dict)

    class DerivedList(db_handlers.CustomGetAllPsopsHandler):
        def handle(self):
            return [WorkflowSearchResult(
                workflow_id=psop.id, workflow_type="psop", name=psop.name,
                description=psop.description, tags=psop.tags, created_at=psop.created_at,
            )]

    class DerivedGet(db_handlers.CustomGetPsopHandler):
        def handle(self, psop_id):
            return psop if psop_id == psop.id else None

    monkeypatch.setattr(HandlerRegistry, "_overrides", dict(HandlerRegistry._overrides))
    monkeypatch.setattr(HandlerRegistry, "_bundled_overrides", dict(
        getattr(HandlerRegistry, "_bundled_overrides", {})), raising=False)
    HandlerRegistry.register(InterfaceType.GET_ALL_PSOP, DerivedList)
    HandlerRegistry.register(InterfaceType.GET_PSOP_BY_ID, DerivedGet)
    retrieval = WorkflowRetrieval(WorkflowStorage(str(tmp_path)), StorageContext(create_backend("mysql")))
    with patch.object(psop_processor, "create_connection", side_effect=AssertionError("extension bypassed")):
        assert retrieval.get_psop_by_id(psop.id) is psop
        assert retrieval.list_recent_workflows(workflow_type="psop")[0].workflow_id == psop.id


def test_cleanup_cannot_replace_classified_outage():
    conn = MagicMock()
    conn.close.side_effect = RuntimeError("private cleanup detail")
    conn.cursor.return_value.execute.side_effect = ConnectionError("query lost")
    conn.cursor.return_value.close.side_effect = RuntimeError("private cursor detail")
    with patch.object(psop_processor, "create_connection", return_value=conn):
        with pytest.raises(StorageUnavailableError):
            psop_processor.get_all_psops()
        with pytest.raises(StorageUnavailableError):
            psop_processor.custom_delete_psop("id")


def test_verified_login_is_not_rejected_by_opportunistic_hash_upgrade_failure():
    row = ("u", "hash", "salt", "user", False, "v2")
    with patch.object(user_store, "create_connection", return_value=MagicMock()), \
         patch.object(user_store, "execute_query", return_value=([row], None)), \
         patch.object(user_store, "_verify_password", return_value=True), \
         patch.object(user_store, "_upgrade_password_scheme", side_effect=StorageUnavailableError("outage")):
        assert user_store.authenticate_user("u", "p")["username"] == "u"


@pytest.mark.anyio
async def test_failed_workflow_save_retains_failure_audit(monkeypatch, sample_psop_dict):
    from fastapi import HTTPException
    from common.log.audit_logger import OperationResult
    from orchestrate.server import frontend_support_server as server

    handler = MagicMock()
    handler.handle.side_effect = StorageUnavailableError("operation unavailable")
    monkeypatch.setattr(server.SharedHandlers, "save_psop", lambda: handler)
    audit = MagicMock()
    monkeypatch.setattr(server.audit_logger, "audit", audit)
    with pytest.raises(HTTPException) as result:
        await server.create_workflow(server.SavePSOPRequest(psop=sample_psop_dict))
    assert result.value.status_code == 503
    assert audit.call_args.args[0]["result"] == OperationResult.FAILURE

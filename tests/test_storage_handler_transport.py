# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Real HTTP/TLS and SQL processors; synthetic DBAPI, not vendor acceptance."""
import asyncio
import socket
import ssl
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest
import uvicorn

from test_storage_http_transport import _tls_files


@pytest.mark.parametrize("mode", ["mysql", "postgresql"])
@pytest.mark.parametrize("transport", ["http", "https"])
def test_handler_crud_uses_one_owned_connection_source(mode, transport, tmp_path, monkeypatch, sample_psop_dict):
    import psycopg2
    from common.util import persistence_mode
    from database.utils import mysql_connection
    from orchestrate.core.shared_handlers import SharedHandlers
    from orchestrate.persistence import context, StorageContext
    from orchestrate.persistence.sql_backend import SqlPersistenceBackend
    from orchestrate.server import frontend_support_server as server, auth, middleware, sse_executor
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    rows = {"psop": {}, "execution_records": {}}
    pools, connections = [], []

    class Pool:
        def __init__(self, config):
            assert config["database"] == "bound_db"
            self.closed = False
            self.close_calls = 0
            pools.append(self)

        def connection(self):
            conn, cursor = MagicMock(), MagicMock()
            conn.cursor.return_value = cursor
            connections.append(conn)

            def execute(sql, params=None):
                sql = " ".join(sql.split())
                table = "execution_records" if "execution_records" in sql else "psop"
                data = rows[table]
                if sql.startswith("INSERT"):
                    assert ("ON DUPLICATE KEY" in sql) == (mode == "mysql")
                    data[params[0]] = params
                    result = []
                elif sql.startswith("DELETE"):
                    cursor.rowcount = int(data.pop(params[0], None) is not None)
                    result = []
                elif sql.startswith("SELECT"):
                    values = [data[params[0]]] if params and params[0] in data else []
                    if not params:
                        values = list(data.values())
                    result = [(row[-1],) for row in values] if "SELECT psop_content" in sql or "SELECT record_content" in sql else values
                else:
                    raise AssertionError("Unexpected SQL: " + sql)
                cursor.fetchall.return_value = result

            cursor.execute.side_effect = execute
            return conn

        def close(self):
            self.closed = True
            self.close_calls += 1

    monkeypatch.setattr(persistence_mode, "get_conf", lambda: {"persistence_mode": "mysql"})
    monkeypatch.setattr(mysql_connection, "MySQLBackend", Pool)
    monkeypatch.setattr(mysql_connection, "get_backend", lambda: pytest.fail("Global pool must not be used"))
    backend = SqlPersistenceBackend(mode, {"connection_config": {"database": "bound_db"}})
    backend._provider._verified = True  # Database bootstrap is outside this routing regression.
    if mode == "postgresql":
        pg_source = Pool({"database": "bound_db"})
        monkeypatch.setattr(psycopg2, "connect", lambda **config: pg_source.connection())
    storage = StorageContext(backend)
    monkeypatch.setattr(context, "_persistence_context", storage)
    for attr in ("_save_handle", "_delete_handle", "_retrieval"):
        monkeypatch.setattr(SharedHandlers, attr, None)
    monkeypatch.setattr(auth, "is_auth_enabled", lambda: False)
    monkeypatch.setattr(server, "audit_logger", MagicMock())
    monkeypatch.setattr(middleware, "limiter", MovingWindowRateLimiter(MemoryStorage()))

    class Engine:
        async def events(self, intent):
            yield {"type": "start", "data": {"psop_id": sample_psop_dict["id"]}}
            yield {"type": "complete", "data": {}}

    monkeypatch.setattr(sse_executor, "OrchestrationEngine", lambda *args, **kwargs: Engine())
    async def consume_execution():
        response = await sse_executor.dispatch_intent_sse([MagicMock()], "synthetic intent")
        assert len([chunk async for chunk in response.body_iterator]) == 2
    asyncio.run(consume_execution())  # Includes the real SSE-finally record handler.
    assert len(rows["execution_records"]) == 1
    record_id = next(iter(rows["execution_records"]))

    monkeypatch.setenv("ORCH_API_TOKEN", "transport-regression-token-000000000000")
    monkeypatch.setattr(auth, "get_conf", lambda: {"external.auth.mode": "bearer"})
    options, verify = {}, True
    if transport == "https":
        cert, key = _tls_files(tmp_path)
        options.update(ssl_certfile=str(cert), ssl_keyfile=str(key))
        verify = ssl.create_default_context(cafile=str(cert))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.listen(32)
    runner = uvicorn.Server(uvicorn.Config(server.app, log_level="error", lifespan="off", **options))
    thread = threading.Thread(target=runner.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not runner.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started
        with httpx.Client(base_url=f"{transport}://127.0.0.1:{port}", verify=verify,
                          trust_env=False, timeout=5,
                          headers={"Authorization": "Bearer transport-regression-token-000000000000"}) as client:
            base = "/rest/v1/orchestrate"
            response = client.post(base + "/workflows", json={"psop": sample_psop_dict})
            assert response.status_code == 201, response.text
            target = base + "/workflows/" + sample_psop_dict["id"]
            assert client.get(target).json()["data"]["id"] == sample_psop_dict["id"]
            assert client.get(base + "/workflows").status_code == 200
            assert client.get("/api/v1/orchestrate/psop/" + sample_psop_dict["id"]).status_code == 200
            assert client.delete(target).status_code == 200
            assert client.get(target).status_code == 404
            for records in (base + "/execution-records", "/api/v1/executions"):
                response = client.get(records)
                assert response.status_code == 200, response.text
                assert response.json()["data"][0]["execution_id"] == record_id
                assert client.get(records + "/" + record_id).status_code == 200
            assert client.delete(base + "/execution-records/" + record_id).status_code == 200
            assert client.get(base + "/execution-records/" + record_id).status_code == 404
    finally:
        runner.should_exit = True
        thread.join(timeout=10)
        listener.close()
        storage.close()
        storage.close()  # Idempotence, without reopening a global fallback.
        assert not thread.is_alive()
    assert rows == {"psop": {}, "execution_records": {}}
    assert all(conn.close.call_count == 1 for conn in connections)
    assert all(conn.cursor.return_value.close.call_count == 1 for conn in connections)
    assert len(pools) == 1
    if mode == "mysql":
        assert pools[0].closed
        assert pools[0].close_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        backend._provider.connection()

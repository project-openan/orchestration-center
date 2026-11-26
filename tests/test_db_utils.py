# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for database/utils/query_execution.py and execution_record_processor.py.

Covers:
- execute_query: None conn, SELECT path, write path, exception path, cursor cleanup
- db_save_execution_record: success, conn None, execute_query error
- db_list_execution_records: success, empty, error, None conn
- db_get_execution_record: found, not found, error, None conn
- db_delete_execution_record: success, not found, error, None conn
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from database.utils.query_execution import execute_query
from orchestrate.persistence.errors import StorageError, StorageUnavailableError, StorageCorruptionError


# ===========================================================================
# execute_query
# ===========================================================================

class TestExecuteQuery:
    def test_none_conn(self):
        result, error = execute_query(None, "SELECT 1")
        assert result is None
        assert isinstance(error, RuntimeError)
        assert "No database connection" in str(error)

    def test_select_returns_results(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [("row1",), ("row2",)]
        conn.cursor.return_value = cur
        result, error = execute_query(conn, "SELECT * FROM users")
        assert error is None
        assert result == [("row1",), ("row2",)]
        cur.fetchall.assert_called_once()
        cur.close.assert_called_once()

    def test_write_commits(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        result, error = execute_query(conn, "INSERT INTO t VALUES (1)")
        assert result is None
        assert error is None
        conn.commit.assert_called_once()
        cur.close.assert_called_once()

    def test_exception_returns_error(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.side_effect = Exception("syntax error")
        conn.cursor.return_value = cur
        result, error = execute_query(conn, "BAD SQL")
        assert result is None
        assert isinstance(error, Exception)
        assert "syntax error" in str(error)
        cur.close.assert_called_once()

    def test_select_with_params(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [("r",)]
        conn.cursor.return_value = cur
        result, error = execute_query(conn, "SELECT * FROM t WHERE id = %s", ("abc",))
        assert error is None
        assert result == [("r",)]
        cur.execute.assert_called_once_with("SELECT * FROM t WHERE id = %s", ("abc",))

    def test_whitespace_stripped(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = []
        conn.cursor.return_value = cur
        execute_query(conn, "   SELECT 1   ")
        cur.execute.assert_called_once_with("SELECT 1", None)


# ===========================================================================
# db_save_execution_record
# ===========================================================================

class TestDbSaveExecutionRecord:
    def test_success(self):
        from orchestrate.handlers.execution_record_processor import db_save_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []
        record = MagicMock()
        record.execution_id = "exec-1"
        record.psop_id = "psop-1"
        record.psop_name = "WF"
        record.started_at = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        record.completed_at = datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
        record.status = "success"
        record.execution_history = []
        record.model_dump_json.return_value = '{"key":"val"}'
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_save_execution_record(record)
            assert result == "exec-1"
            # The columns are timezone-less, so aware values must be bound as naive
            # UTC; otherwise PostgreSQL converts through the session timezone.
            bound = mock_cur.execute.call_args[0][1]
            assert bound[3] == datetime(2025, 1, 1, 0, 0)
            assert bound[3].tzinfo is None
            assert bound[4] == datetime(2025, 1, 1, 1, 0)
            mock_conn.close.assert_called_once()

    def test_conn_none_raises(self):
        from orchestrate.handlers.execution_record_processor import db_save_execution_record
        record = MagicMock()
        record.execution_id = "exec-2"
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=None):
            with pytest.raises(RuntimeError, match="Unable to connect"):
                db_save_execution_record(record)

    def test_query_error_raises(self):
        from orchestrate.handlers.execution_record_processor import db_save_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception("constraint violation")
        mock_conn.cursor.return_value = mock_cur
        record = MagicMock()
        record.execution_id = "exec-3"
        record.psop_id = "psop-1"
        record.psop_name = "WF"
        record.started_at = None
        record.completed_at = None
        record.status = "success"
        record.execution_history = []
        record.model_dump_json.return_value = "{}"
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            with pytest.raises(StorageError, match="Failed to save"):
                db_save_execution_record(record)


# ===========================================================================
# db_list_execution_records
# ===========================================================================

class TestDbListExecutionRecords:
    def test_success(self):
        from orchestrate.handlers.execution_record_processor import db_list_execution_records
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("e1", "psop1", "WF1", None, None, "success", 3, '{"error": null}'),
        ]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_list_execution_records()
            assert len(result) == 1
            assert result[0]["execution_id"] == "e1"
            assert result[0]["psop_name"] == "WF1"
            assert result[0]["error"] is None

    def test_empty_results(self):
        from orchestrate.handlers.execution_record_processor import db_list_execution_records
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_list_execution_records()
            assert result == []

    def test_conn_none_raises(self):
        from orchestrate.handlers.execution_record_processor import db_list_execution_records
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                db_list_execution_records()

    def test_datetimes_converted(self):
        from orchestrate.handlers.execution_record_processor import db_list_execution_records
        import datetime as dt
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        ts = dt.datetime(2025, 1, 1, 12, 0, 0)
        mock_cur.fetchall.return_value = [
            ("e1", "psop1", "WF1", ts, ts, "success", 1, None),
        ]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_list_execution_records()
            assert result[0]["started_at"] == "2025-01-01T12:00:00+00:00"
            assert result[0]["completed_at"] == "2025-01-01T12:00:00+00:00"

    def test_invalid_json_content(self):
        from orchestrate.handlers.execution_record_processor import db_list_execution_records
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("e1", "psop1", "WF1", None, None, "success", 1, "{bad json"),
        ]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            with pytest.raises(StorageCorruptionError):
                db_list_execution_records()


# ===========================================================================
# db_get_execution_record
# ===========================================================================

class TestDbGetExecutionRecord:
    def test_found(self):
        from orchestrate.handlers.execution_record_processor import db_get_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        record_json = '{"execution_id": "e1", "psop_id": "p1", "psop_name": "WF", "started_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T01:00:00", "status": "success", "execution_history": [], "events": [], "final_psop": null, "error": null}'
        mock_cur.fetchall.return_value = [(record_json,)]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_get_execution_record("e1")
            assert result is not None

    def test_not_found(self):
        from orchestrate.handlers.execution_record_processor import db_get_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_get_execution_record("nonexistent")
            assert result is None

    def test_conn_none(self):
        from orchestrate.handlers.execution_record_processor import db_get_execution_record
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                db_get_execution_record("e1")


# ===========================================================================
# db_delete_execution_record
# ===========================================================================

class TestDbDeleteExecutionRecord:
    def test_success(self):
        from orchestrate.handlers.execution_record_processor import db_delete_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 1
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_delete_execution_record("e1")
            assert result is True
            mock_conn.commit.assert_called_once()

    def test_not_found(self):
        from orchestrate.handlers.execution_record_processor import db_delete_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 0
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            result = db_delete_execution_record("nonexistent")
            assert result is False

    def test_conn_none(self):
        from orchestrate.handlers.execution_record_processor import db_delete_execution_record
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                db_delete_execution_record("e1")

    def test_exception_raises(self):
        from orchestrate.handlers.execution_record_processor import db_delete_execution_record
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = ConnectionError("conn lost")
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.execution_record_processor.create_connection", return_value=mock_conn):
            with pytest.raises(StorageUnavailableError):
                db_delete_execution_record("e1")

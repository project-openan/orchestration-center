# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for common/custom/psop_processor.py.

Covers:
- build_tasks_summary: normal, empty, many tasks truncated
- generation_binding: role, instance, mixed and empty workflows
- custom_save_psop: success, conn None, query error
- custom_delete_psop: success, not found, conn None, exception
- get_all_psops: success, empty, error
- get_psop_by_id: found, not found, error
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from orchestrate.persistence.errors import StorageError, StorageUnavailableError

from orchestrate.handlers.psop_processor import (
    build_tasks_summary,
    custom_delete_psop,
    custom_save_psop,
    generation_binding,
    get_all_psops,
    get_psop_by_id,
)


# ---------------------------------------------------------------------------
# build_tasks_summary
# ---------------------------------------------------------------------------

class TestBuildTasksSummary:
    def test_normal(self):
        psop = MagicMock()
        step = MagicMock()
        step.name = "Step1"
        task = MagicMock()
        task.description = "Do A"
        step.subtasks = [task]
        psop.steps = [step]
        result = build_tasks_summary(psop)
        assert result is not None
        assert "[Step1] Do A" in result

    def test_empty_steps(self):
        psop = MagicMock()
        psop.steps = []
        result = build_tasks_summary(psop)
        assert result is None

    def test_empty_subtasks(self):
        psop = MagicMock()
        step = MagicMock()
        step.name = "Step1"
        step.subtasks = []
        psop.steps = [step]
        result = build_tasks_summary(psop)
        assert result is None

    def test_truncates_to_12(self):
        psop = MagicMock()
        step = MagicMock()
        step.name = "Step1"
        tasks = []
        for i in range(20):
            t = MagicMock()
            t.description = f"Task {i}"
            tasks.append(t)
        step.subtasks = tasks
        psop.steps = [step]
        result = build_tasks_summary(psop)
        # Only first 3 subtasks are considered, but slice [:12] caps output
        parts = result.split("; ")
        assert len(parts) <= 12

    def test_only_first_8_steps(self):
        psop = MagicMock()
        steps = []
        for i in range(20):
            s = MagicMock()
            s.name = f"Step{i}"
            t = MagicMock()
            t.description = f"Task {i}"
            s.subtasks = [t]
            steps.append(s)
        psop.steps = steps
        result = build_tasks_summary(psop)
        # Only first 8 steps considered
        assert "[Step0]" in result
        assert "[Step7]" in result
        assert "[Step8]" not in result

    def test_empty_description_skipped(self):
        psop = MagicMock()
        step = MagicMock()
        step.name = "Step1"
        task1 = MagicMock()
        task1.description = ""
        task2 = MagicMock()
        task2.description = "   "
        task3 = MagicMock()
        task3.description = "Real task"
        step.subtasks = [task1, task2, task3]
        psop.steps = [step]
        result = build_tasks_summary(psop)
        assert result is not None
        assert "Real task" in result
        assert len(result.split("; ")) == 1


# ---------------------------------------------------------------------------
# generation_binding
# ---------------------------------------------------------------------------

class TestGenerationBinding:
    def _psop_with_tasks(self, bindings):
        psop = MagicMock()
        psop.steps = []
        for binding in bindings:
            task = MagicMock()
            task.binding = binding
            step = MagicMock()
            step.subtasks = [task]
            psop.steps.append(step)
        return psop

    def test_role_task_marks_role_generation(self):
        assert generation_binding(self._psop_with_tasks(["role"])) == "role"

    def test_mixed_generation_projects_as_role(self):
        assert generation_binding(self._psop_with_tasks(["instance", "role"])) == "role"

    def test_instance_only_generation(self):
        assert generation_binding(self._psop_with_tasks(["instance"])) == "instance"

    def test_workflows_without_binding_default_to_instance(self):
        assert generation_binding(self._psop_with_tasks([])) == "instance"


# ---------------------------------------------------------------------------
# custom_save_psop
# ---------------------------------------------------------------------------

class TestCustomSavePsop:
    def test_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        psop = MagicMock()
        psop.id = "psop-1"
        psop.name = "WF"
        psop.description = "desc"
        psop.model_dump_json.return_value = '{"id":"psop-1"}'
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = custom_save_psop(psop)
            assert result == "psop-1"
            mock_conn.close.assert_called_once()

    def test_conn_none_raises(self):
        psop = MagicMock()
        psop.id = "psop-1"
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=None):
            with pytest.raises(RuntimeError, match="Unable to connect"):
                custom_save_psop(psop)

    def test_query_error_raises(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception("duplicate key")
        mock_conn.cursor.return_value = mock_cur
        psop = MagicMock()
        psop.id = "psop-1"
        psop.name = "WF"
        psop.description = "desc"
        psop.model_dump_json.return_value = "{}"
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            with pytest.raises(StorageError, match="Failed to save PSOP"):
                custom_save_psop(psop)


# ---------------------------------------------------------------------------
# custom_delete_psop
# ---------------------------------------------------------------------------

class TestCustomDeletePsop:
    def test_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 1
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = custom_delete_psop("psop-1")
            assert result is True
            mock_conn.commit.assert_called_once()

    def test_not_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 0
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = custom_delete_psop("nonexistent")
            assert result is False

    def test_conn_none(self):
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                custom_delete_psop("psop-1")

    def test_exception(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = ConnectionError("conn lost")
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            with pytest.raises(StorageUnavailableError):
                custom_delete_psop("psop-1")
            mock_conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# get_all_psops
# ---------------------------------------------------------------------------

class TestGetAllPsops:
    def test_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        psop_json = '{"id": "p1", "name": "WF1", "description": "d", "steps": [], "tags": ["t"], "created_at": "2025-01-01T00:00:00", "user_intent": "ui", "related_preflow": null}'
        mock_cur.fetchall.return_value = [(psop_json,), (psop_json,)]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = get_all_psops()
            assert len(result) == 2
            assert result[0].name == "WF1"

    def test_empty(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            assert get_all_psops() == []

    def test_conn_none(self):
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                get_all_psops()


# ---------------------------------------------------------------------------
# get_psop_by_id
# ---------------------------------------------------------------------------

class TestGetPsopById:
    def test_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        psop_json = '{"id": "p1", "name": "WF1", "description": "d", "steps": [], "tags": ["t"], "created_at": "2025-01-01T00:00:00", "user_intent": "ui", "related_preflow": null}'
        mock_cur.fetchall.return_value = [(psop_json,)]
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = get_psop_by_id("p1")
            assert result is not None
            assert result.name == "WF1"

    def test_not_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cur
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=mock_conn):
            result = get_psop_by_id("nonexistent")
            assert result is None

    def test_conn_none(self):
        with patch("orchestrate.handlers.psop_processor.create_connection", return_value=None):
            with pytest.raises(StorageUnavailableError):
                get_psop_by_id("p1")

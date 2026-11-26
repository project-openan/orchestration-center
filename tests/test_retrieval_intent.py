# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for orchestrate/core/retrieval.py -- intent-based retrieval paths.

Covers:
- _detect_intent_lang: Chinese, English, empty
- _retrieve_names_by_intent: normal, empty summaries, LLM error
- retrieve_psop_by_intent: found, not found, error
- retrieve_psop_by_intent_topn: normal, error
- get_psop_by_preflow: found, not found
- _list_psop_summaries: file mode, DB mode
- _load_psop_by_id: file mode, DB mode
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from orchestrate.core.model.psop import PSOP
from orchestrate.core.retrieval import WorkflowRetrieval, _detect_intent_lang
from orchestrate.persistence.file_backend import FilePsopRepository
from orchestrate.core.psop_vector_index import VectorSettings


@pytest.fixture(autouse=True)
def catalog_retrieval_settings():
    """These tests exercise the catalog path, independently of deployment config."""
    with patch("orchestrate.core.retrieval.vector_settings", return_value=VectorSettings()):
        yield


# ---------------------------------------------------------------------------
# _detect_intent_lang
# ---------------------------------------------------------------------------

class TestDetectIntentLang:
    def test_chinese(self):
        assert _detect_intent_lang("这是一个中文意图") == "Chinese"

    def test_english(self):
        assert _detect_intent_lang("This is an English intent") == "English"

    def test_empty(self):
        assert _detect_intent_lang("") is None

    def test_none(self):
        assert _detect_intent_lang(None) is None

    def test_mixed(self):
        assert _detect_intent_lang("Hello 你好") == "Chinese"


# ---------------------------------------------------------------------------
# WorkflowRetrieval -- file mode helpers
# ---------------------------------------------------------------------------

def _make_storage(psops=None, preflows=None):
    storage = MagicMock()
    psops = psops or []
    preflows = preflows or []
    storage.list_psops.return_value = [p.id for p in psops]
    storage.load_psop.side_effect = lambda wid: next((p for p in psops if p.id == wid), None)
    storage.list_preflows.return_value = [pf.id for pf in preflows]
    storage.load_preflow.side_effect = lambda wid: next((pf for pf in preflows if pf.id == wid), None)
    return storage


def _make_psop(pid="psop-1", name="WF1", description="desc", tags=None,
               user_intent="intent", related_preflow=None):
    psop = MagicMock()
    psop.id = pid
    psop.name = name
    psop.description = description
    psop.tags = tags or ["t"]
    psop.user_intent = user_intent
    psop.related_preflow = related_preflow
    psop.created_at = MagicMock()
    return psop


# ===========================================================================
# get_psop_by_id (file mode)
# ===========================================================================

class TestGetPsopById:
    def test_found(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval.get_psop_by_id("p1")
        assert result is psop

    def test_not_found(self):
        storage = _make_storage([])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval.get_psop_by_id("nonexistent")
        assert result is None


# ===========================================================================
# get_psop_by_preflow
# ===========================================================================

class TestGetPsopByPreflow:
    def test_found(self):
        psop1 = _make_psop("p1", "WF1", related_preflow="pf-1")
        psop2 = _make_psop("p2", "WF2", related_preflow="pf-2")
        storage = _make_storage([psop1, psop2])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval.get_psop_by_preflow("pf-1")
        assert len(result) == 1
        assert result[0].id == "p1"

    def test_not_found(self):
        psop1 = _make_psop("p1", "WF1", related_preflow="pf-2")
        storage = _make_storage([psop1])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval.get_psop_by_preflow("pf-nonexistent")
        assert result == []

    def test_empty_storage(self):
        storage = _make_storage([])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval.get_psop_by_preflow("pf-1")
        assert result == []


# ===========================================================================
# _list_psop_summaries
# ===========================================================================

class TestListPsopSummaries:
    def test_file_mode(self):
        psop = _make_psop("p1", "WF1", tags=["a", "b"])
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            results = retrieval._list_psop_summaries()
            assert len(results) == 1
            assert results[0].name == "WF1"
            assert results[0].workflow_id == "p1"

    def test_db_mode(self):
        # Database mode does not touch the file storage at all: the configured
        # backend's repository answers. This replaced the old HandlerRegistry
        # lookup, so the mock moved to the port.
        storage = _make_storage([])
        repository = MagicMock()
        repository.list_summaries.return_value = [MagicMock(name="DBResult")]
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            mock_ctx.return_value.psops_for.return_value = repository
            retrieval = WorkflowRetrieval(storage)
            results = retrieval._list_psop_summaries()
        assert len(results) == 1
        repository.list_summaries.assert_called_once_with()


# ===========================================================================
# _retrieve_names_by_intent
# ===========================================================================

class TestRetrieveNamesByIntent:
    def test_normal(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch("orchestrate.core.retrieval.get_llm_instance") as mock_llm_fn, \
                 patch("orchestrate.core.retrieval.get_retrieve_psop_prompt") as mock_prompt_fn, \
                 patch("orchestrate.core.retrieval.parse_llm_json_response") as mock_parse:
                mock_llm = MagicMock()
                mock_llm.ask_llm.return_value = (None, "response")
                mock_llm_fn.return_value = mock_llm
                mock_prompt_fn.return_value = "prompt"
                mock_parse.return_value = ["WF1"]
                result = retrieval._retrieve_names_by_intent("do something", top_n=1)
                assert result == ["WF1"]

    def test_empty_summaries(self):
        storage = _make_storage([])
        retrieval = WorkflowRetrieval(storage)
        result = retrieval._retrieve_names_by_intent("test", top_n=1)
        assert result == []

    def test_llm_error_raises(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch("orchestrate.core.retrieval.get_llm_instance") as mock_llm_fn, \
                 patch("orchestrate.core.retrieval.get_retrieve_psop_prompt") as mock_prompt_fn, \
                 patch("orchestrate.core.retrieval.parse_llm_json_response") as mock_parse:
                mock_llm = MagicMock()
                mock_llm.ask_llm.side_effect = RuntimeError("LLM timeout")
                mock_llm_fn.return_value = mock_llm
                mock_prompt_fn.return_value = "prompt"
                with pytest.raises(Exception, match="Failed to retrieve PSOP"):
                    retrieval._retrieve_names_by_intent("test", top_n=1)

    def test_non_list_response_raises(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch("orchestrate.core.retrieval.get_llm_instance") as mock_llm_fn, \
                 patch("orchestrate.core.retrieval.get_retrieve_psop_prompt") as mock_prompt_fn, \
                 patch("orchestrate.core.retrieval.parse_llm_json_response") as mock_parse:
                mock_llm = MagicMock()
                mock_llm.ask_llm.return_value = (None, "response")
                mock_llm_fn.return_value = mock_llm
                mock_prompt_fn.return_value = "prompt"
                mock_parse.return_value = {"not": "a list"}
                with pytest.raises(Exception, match="Expected a JSON array"):
                    retrieval._retrieve_names_by_intent("test", top_n=1)


# ===========================================================================
# retrieve_psop_by_intent
# ===========================================================================

class TestRetrievePsopByIntent:
    def test_found(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=["WF1"]):
                result = retrieval.retrieve_psop_by_intent("do something")
                assert result is psop

    def test_not_found(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=[]):
                result = retrieval.retrieve_psop_by_intent("nonexistent")
                assert result is None

    def test_name_not_in_summaries(self):
        psop = _make_psop("p1", "WF1")
        storage = _make_storage([psop])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=["NonExistentName"]):
                result = retrieval.retrieve_psop_by_intent("test")
                assert result is None

    def test_error_propagates(self):
        storage = _make_storage([])
        retrieval = WorkflowRetrieval(storage)
        with patch.object(retrieval, "_retrieve_names_by_intent", side_effect=Exception("LLM fail")):
            with pytest.raises(Exception, match="Failed to retrieve PSOP"):
                retrieval.retrieve_psop_by_intent("test")


# ===========================================================================
# retrieve_psop_by_intent_topn
# ===========================================================================

class TestRetrievePsopByIntentTopN:
    def test_normal(self):
        psop1 = _make_psop("p1", "WF1")
        psop2 = _make_psop("p2", "WF2")
        storage = _make_storage([psop1, psop2])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=["WF1", "WF2"]):
                result = retrieval.retrieve_psop_by_intent_topn("test", top_n=5)
                assert len(result) == 2
                assert result[0].name == "WF1"

    def test_partial_match(self):
        psop1 = _make_psop("p1", "WF1")
        storage = _make_storage([psop1])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=["WF1", "NonExistent"]):
                result = retrieval.retrieve_psop_by_intent_topn("test", top_n=5)
                assert len(result) == 1

    def test_truncated_to_topn(self):
        psops = [_make_psop(f"p{i}", f"WF{i}") for i in range(10)]
        storage = _make_storage(psops)
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            names = [f"WF{i}" for i in range(10)]
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=names):
                result = retrieval.retrieve_psop_by_intent_topn("test", top_n=3)
                assert len(result) == 3

    def test_error_propagates(self):
        storage = _make_storage([])
        retrieval = WorkflowRetrieval(storage)
        with patch.object(retrieval, "_retrieve_names_by_intent", side_effect=Exception("fail")):
            with pytest.raises(Exception, match="Failed to retrieve PSOP topN"):
                retrieval.retrieve_psop_by_intent_topn("test")


# ===========================================================================
# role/instance generations of one package (shared PSOP name)
# ===========================================================================

SPG_NAME = "IG1526A_Solution_Package.pdf"


def _binding_psop(pid, name, binding, created_at):
    """A real PSOP of the given generation binding; role variants mirror
    what generate-from-preflow stores for role-catalog generations."""
    task = {
        "task_id": f"{pid}-t1",
        "description": "run the task",
        "agent": "role-x" if binding == "role" else "agent-x",
        "skill": "explore",
        "status": "pending",
    }
    psop_kwargs = {
        "id": pid,
        "name": name,
        "description": "variant",
        "created_at": created_at,
        "user_intent": "optimize energy",
        "steps": [{"name": "explore", "type": "AllSuccess", "subtasks": [task], "next": []}],
    }
    if binding == "role":
        task["binding"] = "role"
        task["role_version"] = "1.0.0"
        psop_kwargs["catalog_version"] = "generation-v1"
    return PSOP(**psop_kwargs)


def _variant_storage():
    """One package with role + instance generations plus a superseded role gen,
    and an unrelated workflow for contrast."""
    return _make_storage([
        _binding_psop("role-old", SPG_NAME, "role", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _binding_psop("inst", SPG_NAME, "instance", datetime(2026, 1, 2, tzinfo=timezone.utc)),
        _binding_psop("role", SPG_NAME, "role", datetime(2026, 1, 3, tzinfo=timezone.utc)),
        _binding_psop("other", "Other Workflow", "instance", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ])


def _retrieval_with_variants():
    storage = _variant_storage()
    ctx = MagicMock()
    ctx.psops_for.return_value = FilePsopRepository(storage)
    patcher = patch("orchestrate.core.retrieval.current_context", return_value=ctx)
    patcher.start()
    try:
        return WorkflowRetrieval(storage), patcher
    except Exception:
        patcher.stop()
        raise


class TestRoleInstanceGenerations:
    def test_binding_projects_into_summaries(self):
        retrieval, patcher = _retrieval_with_variants()
        try:
            summaries = {s.workflow_id: s for s in retrieval._list_psop_summaries()}
            assert summaries["role"].binding == "role"
            assert summaries["inst"].binding == "instance"
            assert summaries["other"].binding == "instance"
        finally:
            patcher.stop()

    def test_topn_returns_role_and_instance_as_distinct_results(self):
        retrieval, patcher = _retrieval_with_variants()
        try:
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=[SPG_NAME]):
                results = retrieval.retrieve_psop_by_intent_topn("test", top_n=3)
            # Distinct workflow ids, newest generation first per binding;
            # the superseded role generation is never offered.
            assert [r.workflow_id for r in results] == ["role", "inst"]
            assert {r.binding for r in results} == {"role", "instance"}
        finally:
            patcher.stop()

    def test_topn_dedupes_repeated_names(self):
        """The LLM may repeat a duplicated catalog name; the same workflow
        must not come back twice with an identical id."""
        retrieval, patcher = _retrieval_with_variants()
        try:
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=[SPG_NAME, SPG_NAME]):
                results = retrieval.retrieve_psop_by_intent_topn("test", top_n=3)
            assert [r.workflow_id for r in results] == ["role", "inst"]
        finally:
            patcher.stop()

    def test_topn_truncation_keeps_the_newest_generation(self):
        retrieval, patcher = _retrieval_with_variants()
        try:
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=[SPG_NAME]):
                results = retrieval.retrieve_psop_by_intent_topn("test", top_n=1)
            assert [r.workflow_id for r in results] == ["role"]
        finally:
            patcher.stop()

    def test_single_retrieval_picks_the_newest_generation(self):
        retrieval, patcher = _retrieval_with_variants()
        try:
            with patch.object(retrieval, "_retrieve_names_by_intent", return_value=[SPG_NAME]):
                result = retrieval.retrieve_psop_by_intent("test")
            assert result.id == "role"
        finally:
            patcher.stop()

    def test_catalog_only_offers_live_generations_with_binding(self):
        retrieval, patcher = _retrieval_with_variants()
        try:
            with patch("orchestrate.core.retrieval.get_llm_instance") as mock_llm_fn, \
                 patch("orchestrate.core.retrieval.get_retrieve_psop_prompt") as mock_prompt_fn, \
                 patch("orchestrate.core.retrieval.parse_llm_json_response", return_value=[]):
                mock_llm = MagicMock()
                mock_llm.ask_llm.return_value = (None, "[]")
                mock_llm_fn.return_value = mock_llm
                mock_prompt_fn.return_value = "prompt"
                retrieval._retrieve_names_by_intent("test", top_n=3)
            rows = json.loads(mock_prompt_fn.call_args[0][1])
            by_id = {row["id"]: row for row in rows}
            assert set(by_id) == {"role", "inst", "other"}
            assert by_id["role"]["binding"] == "role"
            assert by_id["inst"]["binding"] == "instance"
        finally:
            patcher.stop()


# ===========================================================================
# search_by_name
# ===========================================================================

class TestSearchByName:
    def test_psop_match(self):
        psop1 = _make_psop("p1", "SummarizeWF")
        psop2 = _make_psop("p2", "TranslateWF")
        storage = _make_storage([psop1, psop2])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            results = retrieval.search_by_name("summarize")
            assert len(results) == 1
            assert results[0].name == "SummarizeWF"

    def test_no_match(self):
        psop1 = _make_psop("p1", "WF1")
        storage = _make_storage([psop1])
        retrieval = WorkflowRetrieval(storage)
        with patch("orchestrate.core.retrieval.current_context") as mock_ctx:
            # File mode reads the storage this retrieval object was given.
            mock_ctx.return_value.psops_for.return_value = FilePsopRepository(storage)
            results = retrieval.search_by_name("nonexistent")
            assert results == []

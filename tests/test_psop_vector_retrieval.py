# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the optional embedding recall path in orchestrate/core/retrieval.py.

The switch is the contract: with ``retrieval.vector.enabled`` off the retrieval
behaviour must stay byte-for-byte identical to the LLM-only path.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import MagicMock, patch

import pytest

from orchestrate.core.psop_vector_index import VectorSettings
from orchestrate.core.retrieval import WorkflowRetrieval
from orchestrate.core.workflow_search_result import WorkflowSearchResult
from common.llm.config.llm_config import ModelConfig


@pytest.fixture(autouse=True)
def synthetic_embedding_config():
    """Never read a developer's model settings in deterministic retrieval tests."""
    with patch("common.llm.config.llm_config.get_model_config", return_value=ModelConfig(
        model="synthetic-embed", url="https://example.invalid/embed", body={"input": "$PROMPT"},
    )) as config:
        yield config


CORE = "Core Network Fault Management"
TRANSPORT = "Transport Network Fault Management"


def _summary(workflow_id, name, description):
    return WorkflowSearchResult(
        workflow_id=workflow_id,
        workflow_type="psop",
        name=name,
        description=description,
        tags=["an-l4"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_intent=description,
        tasks_summary=f"{description} steps",
    )


def _fake_embed(text):
    """Deterministic three-dimensional 'semantic' space."""
    lowered = text.lower()
    if "core" in lowered or "核心" in lowered:
        return [1.0, 0.0, 0.0]
    if "transport" in lowered or "承载" in lowered:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


class _CountingEmbedder:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def embed(self, text):
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("embedding endpoint unavailable")
        return _fake_embed(text)


class _FakeLLM:
    def __init__(self, names):
        self.names = names
        self.calls = []

    def ask_llm(self, prompt):
        self.calls.append(prompt)
        return "", json.dumps(self.names)


def _retrieval():
    return WorkflowRetrieval(MagicMock())


def _summaries():
    return [
        _summary("core", CORE, "core network"),
        _summary("transport", TRANSPORT, "transport network"),
    ]


def _settings(tmp_path, **overrides):
    base = dict(
        enabled=True,
        top_k=20,
        min_score=0.0,
        rerank=False,
        llm_final=True,
        strict=False,
        index_file=str(tmp_path / "psop_vectors.json"),
        thinking=True,
    )
    base.update(overrides)
    return VectorSettings(**base)


# ---------------------------------------------------------------------------
# switch off: unchanged behaviour
# ---------------------------------------------------------------------------

class TestSwitchOff:
    def test_llm_path_is_used_and_embeddings_are_never_called(self, tmp_path):
        retrieval = _retrieval()
        embedder = _CountingEmbedder()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path, enabled=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_retrieve_names_by_intent", return_value=[CORE]), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            results = retrieval.retrieve_psop_by_intent_topn("任意意图", top_n=3)

        assert [result.workflow_id for result in results] == ["core"]
        assert embedder.calls == []


# ---------------------------------------------------------------------------
# switch on: recall -> optional rerank -> final choice
# ---------------------------------------------------------------------------

class TestVectorPath:
    def test_queries_embed_concurrently_but_share_one_complete_index(self, tmp_path):
        retrieval = _retrieval()
        queries = Barrier(2)
        embedder = MagicMock()

        def embed(text):
            if not text.startswith("name:"):
                queries.wait(timeout=3)
            return _fake_embed(text)

        embedder.embed.side_effect = embed
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, llm_final=False, strict=True)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder), \
             ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(retrieval.retrieve_psop_by_intent_topn, "core query") for _ in range(2)]
            assert [[r.workflow_id for r in future.result(timeout=5)] for future in futures] == [
                ["core", "transport"], ["core", "transport"],
            ]
        assert embedder.embed.call_count == 4  # two queries, documents built only once

    @pytest.mark.parametrize("field,value", [
        ("url", "https://other.invalid/embed"),
        ("body", {"input": "$PROMPT", "dimensions": 3}),
        ("response", {"embedding": "vectors[0]"}),
    ])
    def test_vector_space_config_change_invalidates_same_dimension_cache(
        self, tmp_path, synthetic_embedding_config, field, value,
    ):
        retrieval = _retrieval()
        embedder = _CountingEmbedder()
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, llm_final=False)), \
             patch.object(WorkflowRetrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            retrieval.retrieve_psop_by_intent_topn("core query")
            setattr(synthetic_embedding_config.return_value, field, value)
            embedder.calls.clear()
            retrieval.retrieve_psop_by_intent_topn("core query")
            assert len(embedder.calls) == 3
            # Persisted identity also protects a process restarted after a switch.
            synthetic_embedding_config.return_value.url = "https://third.invalid/embed"
            embedder.calls.clear()
            _retrieval().retrieve_psop_by_intent_topn("core query")
            assert len(embedder.calls) == 3
        cache = (tmp_path / "psop_vectors.json").read_text()
        assert "third.invalid" not in cache
        assert "dimensions" not in cache

    def test_auth_rotation_does_not_invalidate_vectors(self, tmp_path, synthetic_embedding_config):
        retrieval = _retrieval()
        embedder = _CountingEmbedder()
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            retrieval.retrieve_psop_by_intent_topn("core query")
            synthetic_embedding_config.return_value.api_key = "synthetic-rotated-secret"
            embedder.calls.clear()
            retrieval.retrieve_psop_by_intent_topn("core query")
        assert len(embedder.calls) == 1
        assert "synthetic-rotated-secret" not in (tmp_path / "psop_vectors.json").read_text()

    def test_recall_then_llm_final_choice(self, tmp_path):
        retrieval = _retrieval()
        embedder = _CountingEmbedder()
        llm = _FakeLLM([CORE])
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=llm):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        assert [result.workflow_id for result in results] == ["core"]
        assert len(llm.calls) == 1
        # Two PSOP documents plus one query embedding on a cold index.
        assert len(embedder.calls) == 3

    def test_llm_final_can_be_switched_off(self, tmp_path):
        retrieval = _retrieval()
        llm = _FakeLLM(["unused"])
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", side_effect=AssertionError("LLM must not run")):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        # Vector order: exact match first, unrelated second.
        assert [result.workflow_id for result in results] == ["core", "transport"]
        assert llm.calls == []

    def test_index_is_reused_between_calls(self, tmp_path):
        retrieval = _retrieval()
        embedder = _CountingEmbedder()
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)
            first_pass = len(embedder.calls)
            retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert first_pass == 3
        # Only the new query is embedded; the PSOP catalog stays cached.
        assert len(embedder.calls) == 4

    def test_empty_recall_falls_back_to_the_catalog(self, tmp_path):
        """A min_score above the corpus similarity must not read as "no match"."""
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, min_score=0.9, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_retrieve_names_by_intent", return_value=[CORE]) as catalog, \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()):
            results = retrieval.retrieve_psop_by_intent_topn("完全无关的意图", top_n=2)

        assert [result.workflow_id for result in results] == ["core"]
        catalog.assert_called_once()

    def test_single_result_api_uses_the_vector_path(self, tmp_path):
        retrieval = _retrieval()
        sentinel = object()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_load_psop_by_id", return_value=sentinel) as loader, \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM([CORE])):
            result = retrieval.retrieve_psop_by_intent("核心网故障处理")

        assert result is sentinel
        loader.assert_called_once_with("core")


# ---------------------------------------------------------------------------
# rerank
# ---------------------------------------------------------------------------

class TestRerank:
    def test_reranker_order_wins(self, tmp_path):
        retrieval = _retrieval()
        reranker = MagicMock()
        reranker.rerank.return_value = [
            {"index": 1, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.1},
        ]
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, rerank=True, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_rerank_instance", return_value=reranker):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["transport", "core"]
        assert results[0].score == pytest.approx(0.9)

    def test_reranker_failure_keeps_vector_order(self, tmp_path):
        retrieval = _retrieval()
        reranker = MagicMock()
        reranker.rerank.side_effect = RuntimeError("rerank down")
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, rerank=True, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_rerank_instance", return_value=reranker):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core", "transport"]

    def test_empty_rerank_result_keeps_vector_order(self, tmp_path):
        retrieval = _retrieval()
        reranker = MagicMock()
        reranker.rerank.return_value = []
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, rerank=True, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_rerank_instance", return_value=reranker):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core", "transport"]


# ---------------------------------------------------------------------------
# failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    @pytest.mark.parametrize("single", [False, True])
    def test_explicit_no_match_is_not_replaced_by_vector_candidates(self, tmp_path, single):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_retrieve_names_by_intent") as catalog, \
             patch.object(retrieval, "_load_psop_by_id") as loader, \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM([])):
            if single:
                assert retrieval.retrieve_psop_by_intent("unrelated intent") is None
            else:
                assert retrieval.retrieve_psop_by_intent_topn("unrelated intent") == []
        catalog.assert_not_called()
        loader.assert_not_called()

    @pytest.mark.parametrize("strict", [False, True])
    @pytest.mark.parametrize("restart", [False, True])
    def test_query_dimension_drift_rebuilds_unchanged_catalog(self, tmp_path, strict, restart):
        retrieval = _retrieval()
        settings = _settings(tmp_path, strict=strict, llm_final=False)
        dimension = 2
        embedder = MagicMock()
        embedder.embed.side_effect = lambda _: [1.0] + [0.0] * (dimension - 1)
        with patch("orchestrate.core.retrieval.vector_settings", return_value=settings), \
             patch.object(WorkflowRetrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(WorkflowRetrieval, "_retrieve_names_by_intent") as catalog, \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            retrieval.retrieve_psop_by_intent_topn("core query")
            dimension = 3
            if restart:
                retrieval = _retrieval()
            embedder.reset_mock()
            results = retrieval.retrieve_psop_by_intent_topn("core query")
            assert [r.workflow_id for r in results] == ["core", "transport"]
            assert embedder.embed.call_count == 3  # query + two documents, no retry loop
            retrieval.retrieve_psop_by_intent_topn("core query")
            assert embedder.embed.call_count == 4  # rebuilt cache is reused
            catalog.assert_not_called()
        assert json.loads((tmp_path / "psop_vectors.json").read_text())["dim"] == 3

    @pytest.mark.parametrize("strict", [False, True])
    def test_inconsistent_query_provider_has_bounded_recovery(self, tmp_path, strict):
        retrieval = _retrieval()
        embedder = MagicMock()
        embedder.embed.side_effect = lambda text: [1.0, 0.0] if text.startswith("name:") else [1.0, 0.0, 0.0]
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, strict=strict, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_retrieve_names_by_intent", return_value=[CORE]) as catalog, \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=embedder):
            if strict:
                with pytest.raises(ValueError, match="dimension"):
                    retrieval.retrieve_psop_by_intent_topn("core query")
                catalog.assert_not_called()
            else:
                assert retrieval.retrieve_psop_by_intent_topn("core query")[0].workflow_id == "core"
                catalog.assert_called_once()
        assert embedder.embed.call_count == 5  # initial docs + query + one rebuild only

    def test_embedding_failure_falls_back_to_the_llm_path(self, tmp_path):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch.object(retrieval, "_retrieve_names_by_intent", return_value=[TRANSPORT]), \
             patch("orchestrate.core.retrieval.get_embed_instance",
                   return_value=_CountingEmbedder(fail=True)):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        assert [result.workflow_id for result in results] == ["transport"]

    def test_strict_mode_propagates_the_failure(self, tmp_path):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, strict=True)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance",
                   return_value=_CountingEmbedder(fail=True)):
            with pytest.raises(RuntimeError, match="embedding endpoint unavailable"):
                retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

    def test_llm_final_failure_keeps_vector_order(self, tmp_path):
        retrieval = _retrieval()
        broken = MagicMock()
        broken.ask_llm.side_effect = RuntimeError("llm down")
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=broken):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core", "transport"]

    def test_llm_naming_nothing_relevant_keeps_vector_order(self, tmp_path):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM(["Not A Candidate"])):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core", "transport"]


# ---------------------------------------------------------------------------
# duplicate handling: shared names and repeated rerank indexes
# ---------------------------------------------------------------------------

class TestDuplicateHandling:
    """Two PSOPs can share a name, and a reranker can repeat an index."""

    def _same_name_summaries(self):
        return [
            _summary("core-v1", CORE, "core network"),
            _summary("core-v2", CORE, "core network backup"),
        ]

    def test_duplicate_rerank_index_does_not_repeat_a_psop(self, tmp_path):
        retrieval = _retrieval()
        reranker = MagicMock()
        reranker.rerank.return_value = [
            {"index": 0, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.8},
        ]
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, rerank=True, llm_final=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_rerank_instance", return_value=reranker):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core"]

    def test_duplicate_names_keep_the_better_ranked_psop(self, tmp_path):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries",
                          return_value=self._same_name_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM([CORE])):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        assert [result.workflow_id for result in results] == ["core-v1"]

    def test_selection_resolves_an_id_token(self, tmp_path):
        """The prompt carries the id, so honour it when the model echoes one."""
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries",
                          return_value=self._same_name_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM(["core-v2"])):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        assert [result.workflow_id for result in results] == ["core-v2"]

    def test_repeated_selection_does_not_repeat_a_psop(self, tmp_path):
        retrieval = _retrieval()
        with patch("orchestrate.core.retrieval.vector_settings", return_value=_settings(tmp_path)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=_FakeLLM([CORE, CORE])):
            results = retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=2)

        assert [result.workflow_id for result in results] == ["core"]


# ---------------------------------------------------------------------------
# thinking control for retrieval calls
# ---------------------------------------------------------------------------

class TestRetrievalThinking:
    @pytest.mark.parametrize("enabled,fail", [(False, False), (True, True)])
    def test_catalog_and_failure_fallback_respect_thinking_policy(self, tmp_path, enabled, fail):
        retrieval = _retrieval()
        llm = _FakeLLM([CORE])
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, enabled=enabled, thinking=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder(fail=fail)), \
             patch("orchestrate.core.retrieval.get_llm_instance") as shared, \
             patch("orchestrate.core.retrieval.get_chat_instance_with_body", return_value=llm) as extended:
            assert retrieval.retrieve_psop_by_intent_topn("core query")[0].workflow_id == "core"
        shared.assert_not_called()
        extended.assert_called_once_with("retrieval_no_thinking", {"thinking": {"type": "disabled"}})
        assert len(llm.calls) == 1

    def test_thinking_enabled_uses_the_shared_chat_instance(self, tmp_path):
        retrieval = _retrieval()
        llm = _FakeLLM([CORE])
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, thinking=True)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_llm_instance", return_value=llm) as shared, \
             patch("orchestrate.core.retrieval.get_chat_instance_with_body") as extended:
            retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        shared.assert_called_once()
        extended.assert_not_called()

    def test_thinking_disabled_requests_an_extended_body(self, tmp_path):
        retrieval = _retrieval()
        llm = _FakeLLM([CORE])
        with patch("orchestrate.core.retrieval.vector_settings",
                   return_value=_settings(tmp_path, thinking=False)), \
             patch.object(retrieval, "_list_psop_summaries", return_value=_summaries()), \
             patch("orchestrate.core.retrieval.get_embed_instance", return_value=_CountingEmbedder()), \
             patch("orchestrate.core.retrieval.get_chat_instance_with_body", return_value=llm) as extended:
            retrieval.retrieve_psop_by_intent_topn("核心网故障处理", top_n=1)

        extended.assert_called_once_with("retrieval_no_thinking", {"thinking": {"type": "disabled"}})
        assert llm.calls

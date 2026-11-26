# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for orchestrate/core/psop_vector_index.py.

Covers:
- psop_document / content_hash: field coverage and edit sensitivity
- cosine: identical, orthogonal, zero vector, dimension mismatch
- VectorSettings.from_config: defaults, parsing, invalid values
- PsopVectorIndex: first-build, cache reuse, edit invalidation, deletion pruning,
  persistence round-trip, model change, dimension change, empty embedding
- PsopVectorIndex.search: ordering, top_k, min_score, stable ties
"""

import json
from datetime import datetime, timezone

import pytest

from orchestrate.core.psop_vector_index import (
    PsopVectorIndex,
    VectorSettings,
    content_hash,
    cosine,
    psop_document,
)
from orchestrate.core.workflow_search_result import WorkflowSearchResult


def _summary(workflow_id="psop-1", name="Core Network Fault", description="core network",
             tags=None, user_intent="core fault", tasks="diagnose core"):
    return WorkflowSearchResult(
        workflow_id=workflow_id,
        workflow_type="psop",
        name=name,
        description=description,
        tags=tags or ["core"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user_intent=user_intent,
        tasks_summary=tasks,
    )


# ---------------------------------------------------------------------------
# document text + hashing
# ---------------------------------------------------------------------------

class TestDocument:
    def test_document_carries_every_prompt_field(self):
        document = psop_document(_summary())
        assert "Core Network Fault" in document
        assert "core network" in document
        assert "core" in document
        assert "core fault" in document
        assert "diagnose core" in document

    def test_hash_is_stable_and_edit_sensitive(self):
        assert content_hash("abc") == content_hash("abc")
        assert content_hash("abc") != content_hash("abd")

    def test_hash_changes_when_description_changes(self):
        first = content_hash(psop_document(_summary(description="one")))
        second = content_hash(psop_document(_summary(description="two")))
        assert first != second


# ---------------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors(self):
        assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_scores_zero(self):
        assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_dimension_mismatch_raises(self):
        with pytest.raises(ValueError, match="dimensions"):
            cosine([1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

class TestVectorSettings:
    def test_defaults_keep_vector_search_off(self):
        settings = VectorSettings()
        assert settings.enabled is False
        assert settings.top_k == 5
        assert settings.min_score == 0.0
        assert settings.rerank is False
        assert settings.llm_final is True
        assert settings.strict is False
        assert settings.thinking is True

    def test_reads_each_documented_key(self):
        conf = {
            "retrieval.vector.enabled": "true",
            "retrieval.vector.top_k": "7",
            "retrieval.vector.min_score": "0.25",
            "retrieval.vector.rerank": "yes",
            "retrieval.vector.llm_final": "false",
            "retrieval.vector.strict": "on",
            "retrieval.vector.index_file": "data/x.json",
            "retrieval.llm.thinking": "false",
        }
        settings = VectorSettings.from_config(conf)
        assert settings.enabled is True
        assert settings.top_k == 7
        assert settings.min_score == 0.25
        assert settings.rerank is True
        assert settings.llm_final is False
        assert settings.strict is True
        assert settings.index_file == "data/x.json"
        assert settings.thinking is False

    def test_rejects_non_numeric_top_k(self):
        with pytest.raises(ValueError, match="retrieval.vector.top_k"):
            VectorSettings.from_config({"retrieval.vector.top_k": "many"})

    def test_rejects_non_positive_top_k(self):
        with pytest.raises(ValueError, match=">= 1"):
            VectorSettings.from_config({"retrieval.vector.top_k": "0"})


# ---------------------------------------------------------------------------
# index lifecycle
# ---------------------------------------------------------------------------

class TestReconcile:
    def test_version_one_cache_is_rebuilt_once(self, tmp_path):
        path = tmp_path / "idx.json"
        summary = _summary("a")
        path.write_text(json.dumps({
            "version": 1, "model": "m", "dim": 2,
            "entries": {"a": {"hash": content_hash(psop_document(summary)), "vector": [0.0, 1.0]}},
        }), encoding="utf-8")
        calls = []
        embed = lambda text: (calls.append(text), [1.0, 0.0])[1]
        PsopVectorIndex(path, model="m").reconcile([summary], embed)
        PsopVectorIndex(path, model="m").reconcile([summary], embed)
        assert len(calls) == 1
        assert json.loads(path.read_text())["version"] == 2

    def test_failed_rebuild_preserves_previous_complete_generation(self, tmp_path):
        path = tmp_path / "idx.json"
        index = PsopVectorIndex(path, model="m")
        summaries = [_summary("a"), _summary("b")]
        index.reconcile(summaries, lambda _: [1.0, 0.0])
        original = path.read_bytes()
        calls = []

        def broken(text):
            calls.append(text)
            if len(calls) == 3:
                raise RuntimeError("provider unavailable midway")
            return [1.0, 0.0, 0.0]

        with pytest.raises(RuntimeError, match="midway"):
            # First embedding detects drift; the rebuild fails after one row.
            index.reconcile([_summary("a", description="changed"), _summary("b")], broken)
        assert path.read_bytes() == original
        assert [wid for wid, _ in index.search([1.0, 0.0], top_k=2)] == ["a", "b"]

    @pytest.mark.parametrize("vector", [[float("nan"), 0], [float("inf"), 0], [True, 0], ["1", 0]])
    def test_invalid_provider_vectors_never_enter_cache(self, tmp_path, vector):
        path = tmp_path / "idx.json"
        index = PsopVectorIndex(path, model="m")
        with pytest.raises(ValueError, match="invalid vector"):
            index.reconcile([_summary("a")], lambda _: vector)
        assert not path.exists()

    @pytest.mark.parametrize("vector", [[1.0], ["1", 0], [True, 0], [10**400, 0], [float("nan"), 0],
                                       [float("inf"), 0], None, {"bad": 1}])
    def test_malformed_cached_row_is_reembedded_not_silently_dropped(self, tmp_path, vector):
        path = tmp_path / "idx.json"
        summaries = [_summary("a"), _summary("b")]
        PsopVectorIndex(path, model="m").reconcile(summaries, lambda _: [1.0, 0.0])
        payload = json.loads(path.read_text())
        payload["entries"]["a"]["vector"] = vector
        path.write_text(json.dumps(payload), encoding="utf-8")
        calls = []
        index = PsopVectorIndex(path, model="m")
        index.reconcile(summaries, lambda text: (calls.append(text), [1.0, 0.0])[1])
        assert len(calls) == 1
        assert [wid for wid, _ in index.search([1.0, 0.0], top_k=2)] == ["a", "b"]

    @pytest.mark.parametrize("payload", [[], None, "invalid", 4])
    def test_non_object_json_cache_is_rebuilt(self, tmp_path, payload):
        path = tmp_path / "idx.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        index = PsopVectorIndex(path, model="m")
        index.reconcile([_summary("a")], lambda _: [1.0, 0.0])
        assert index.search([1.0, 0.0], top_k=1)[0][0] == "a"

    def test_first_pass_embeds_every_psop(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        calls = []

        def embed(text):
            calls.append(text)
            return [1.0, 0.0]

        index.reconcile([_summary("a"), _summary("b")], embed)
        assert len(calls) == 2

    def test_second_pass_reuses_cache(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        calls = []
        embed = lambda text: (calls.append(text), [1.0, 0.0])[1]
        summaries = [_summary("a"), _summary("b")]
        index.reconcile(summaries, embed)
        calls.clear()
        index.reconcile(summaries, embed)
        assert calls == []

    def test_edited_psop_is_reembedded_alone(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        calls = []
        embed = lambda text: (calls.append(text), [1.0, 0.0])[1]
        index.reconcile([_summary("a"), _summary("b")], embed)
        calls.clear()
        index.reconcile([_summary("a"), _summary("b", description="changed")], embed)
        assert len(calls) == 1

    def test_deleted_psop_is_pruned_from_search(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        embed = lambda text: [1.0, 0.0]
        index.reconcile([_summary("a"), _summary("b")], embed)
        index.reconcile([_summary("a")], embed)
        hits = index.search([1.0, 0.0], top_k=10)
        assert [workflow_id for workflow_id, _ in hits] == ["a"]

    def test_cache_survives_a_new_instance(self, tmp_path):
        path = tmp_path / "idx.json"
        PsopVectorIndex(path, model="m").reconcile([_summary("a")], lambda text: [1.0, 0.0])
        calls = []
        embed = lambda text: (calls.append(text), [1.0, 0.0])[1]
        PsopVectorIndex(path, model="m").reconcile([_summary("a")], embed)
        assert calls == []

    def test_model_change_discards_the_cache(self, tmp_path):
        path = tmp_path / "idx.json"
        PsopVectorIndex(path, model="model-a").reconcile([_summary("a")], lambda text: [1.0, 0.0])
        calls = []
        embed = lambda text: (calls.append(text), [0.0, 1.0])[1]
        PsopVectorIndex(path, model="model-b").reconcile([_summary("a")], embed)
        assert len(calls) == 1

    def test_dimension_change_rebuilds_every_vector(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        index.reconcile([_summary("a"), _summary("b")], lambda text: [1.0, 0.0])
        calls = []

        def embed(text):
            calls.append(text)
            return [1.0, 0.0, 0.0]

        # An edited document forces one embed, which reveals the new dimension and
        # triggers a full rebuild of the remaining catalog.
        index.reconcile([_summary("a", description="edited"), _summary("b")], embed)
        assert len(calls) == 3
        assert index.search([1.0, 0.0, 0.0], top_k=5)

    def test_empty_embedding_is_an_error(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        with pytest.raises(ValueError, match="empty vector"):
            index.reconcile([_summary("a")], lambda text: [])

    def test_corrupt_cache_is_ignored(self, tmp_path):
        path = tmp_path / "idx.json"
        path.write_text("{not json", encoding="utf-8")
        index = PsopVectorIndex(path, model="m")
        index.reconcile([_summary("a")], lambda text: [1.0, 0.0])
        assert [workflow_id for workflow_id, _ in index.search([1.0, 0.0], top_k=5)] == ["a"]

    def test_unwritable_cache_does_not_break_search(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("file, not a directory", encoding="utf-8")
        index = PsopVectorIndex(blocker / "nested" / "idx.json", model="m")
        index.reconcile([_summary("a")], lambda text: [1.0, 0.0])
        assert [workflow_id for workflow_id, _ in index.search([1.0, 0.0], top_k=5)] == ["a"]


class TestSearch:
    def _index(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        vectors = {
            "core": [1.0, 0.0],
            "transport": [0.0, 1.0],
            "core2": [0.9, 0.1],
        }
        index.reconcile(
            [_summary("core", description="core"), _summary("transport", description="transport"),
             _summary("core2", description="core2")],
            lambda text: vectors[text.split("description: ")[1].split("\n")[0]],
        )
        return index

    def test_orders_by_similarity(self, tmp_path):
        index = self._index(tmp_path)
        hits = index.search([1.0, 0.0], top_k=3)
        assert [workflow_id for workflow_id, _ in hits][:2] == ["core", "core2"]

    def test_respects_top_k(self, tmp_path):
        index = self._index(tmp_path)
        assert len(index.search([1.0, 0.0], top_k=1)) == 1

    def test_min_score_filters(self, tmp_path):
        index = self._index(tmp_path)
        hits = index.search([1.0, 0.0], top_k=10, min_score=0.995)
        assert [workflow_id for workflow_id, _ in hits] == ["core"]

    def test_ties_break_on_workflow_id(self, tmp_path):
        index = PsopVectorIndex(tmp_path / "idx.json", model="m")
        index.reconcile([_summary("b"), _summary("a")], lambda text: [1.0, 0.0])
        assert [workflow_id for workflow_id, _ in index.search([1.0, 0.0], top_k=5)] == ["a", "b"]

    def test_query_of_another_dimension_raises_instead_of_going_empty(self, tmp_path):
        index = self._index(tmp_path)
        with pytest.raises(ValueError, match="does not match the index dimension"):
            index.search([1.0, 0.0, 0.0], top_k=5)

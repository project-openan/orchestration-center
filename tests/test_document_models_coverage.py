# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
"""Direct coverage for DocumentPreflowRepository save/get/list/delete paths."""

import pytest

from orchestrate.core.model.preflow import PreFlow
from orchestrate.persistence.document_models import DocumentPreflowRepository
from orchestrate.persistence.errors import StorageCorruptionError


class _FakeDocuments:
    def __init__(self):
        self._data = {"preflows": {}}

    def save(self, kind, doc_id, value):
        self._data.setdefault(kind, {})[doc_id] = value

    def get(self, kind, doc_id):
        return self._data.get(kind, {}).get(doc_id)

    def list(self, kind):
        return list(self._data.get(kind, {}).values())

    def delete(self, kind, doc_id):
        return self._data.get(kind, {}).pop(doc_id, None) is not None


def _preflow(doc_id="pf-1"):
    return PreFlow(id=doc_id, name="Workflow", steps_md="# Steps")


class TestDocumentPreflowRepository:
    def test_save_then_get_round_trips(self):
        repo = DocumentPreflowRepository(_FakeDocuments())
        preflow = _preflow("pf-roundtrip")
        assert repo.save(preflow) == preflow.id
        loaded = repo.get(preflow.id)
        assert loaded is not None
        assert loaded.id == preflow.id
        assert loaded.name == "Workflow"

    def test_get_missing_returns_none(self):
        repo = DocumentPreflowRepository(_FakeDocuments())
        assert repo.get("absent") is None

    def test_get_corrupt_payload_raises_storage_corruption(self):
        docs = _FakeDocuments()
        repo = DocumentPreflowRepository(docs)
        docs.save("preflows", "bad", {"id": "bad"})
        with pytest.raises(StorageCorruptionError):
            repo.get("bad")

    def test_list_ids_returns_stored_ids(self):
        repo = DocumentPreflowRepository(_FakeDocuments())
        repo.save(_preflow("pf-a"))
        repo.save(_preflow("pf-b"))
        assert sorted(repo.list_ids()) == ["pf-a", "pf-b"]

    def test_list_ids_corrupt_payload_raises_storage_corruption(self):
        docs = _FakeDocuments()
        repo = DocumentPreflowRepository(docs)
        docs.save("preflows", "bad", {"id": "bad"})
        with pytest.raises(StorageCorruptionError):
            repo.list_ids()

    def test_delete_returns_bool(self):
        repo = DocumentPreflowRepository(_FakeDocuments())
        preflow = _preflow("pf-del")
        repo.save(preflow)
        assert repo.delete(preflow.id) is True
        assert repo.delete(preflow.id) is False

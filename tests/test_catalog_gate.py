# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Sub-requirement 2: save-time catalog gate and persistence-chain roundtrip.

Covers the two remaining acceptance items: catalog reference validation wired
into the save entry, and the new role fields surviving the real file-mode
persistence chain.
"""

import pytest

from orchestrate.core.catalog_gate import CatalogGate, ensure_role_references_authorized
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.persistence.errors import RoleReferenceError
from orchestrate.server.storage_error_response import storage_http_exception

SOURCE = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])


def approved_catalog(role_id="optimizer", skill_ids=("explore",), status="approved"):
    return RoleCatalog.model_validate(dict(
        catalog_version="pilot-v1",
        roles=[dict(
            role_id=role_id, role_version="1", name="Optimizer",
            description="Synthetic test role", source=SOURCE, review_status=status,
            skills=[dict(skill_id=s, name=s, description=s, source=SOURCE, review_status=status)
                    for s in skill_ids],
        )],
    ))


def make_role_psop(agent="optimizer", skill="explore", catalog_version="pilot-v1"):
    return PSOP.model_validate(dict(
        id=f"wf-{agent}-{skill}", name="Role demo", catalog_version=catalog_version,
        steps=[dict(name="optimize", subtasks=[dict(
            task_id="t1", description="Explore intent", binding="role",
            agent=agent, skill=skill, role_version="1",
        )])],
    ))


def make_instance_psop():
    return PSOP.model_validate(dict(
        id="wf-legacy", name="Legacy",
        steps=[dict(name="work", subtasks=[dict(
            task_id="t1", description="Do work", binding="instance",
            agent="Existing Agent", skill="Existing Skill",
        )])],
    ))


class RecordingHandler:
    def __init__(self):
        self.saved = []

    def handle(self, psop):
        self.saved.append(psop.id)
        return psop.id


class StorageHandlerAdapter:
    """Adapts WorkflowStorage to the dispatch-handler interface."""

    def __init__(self, storage):
        self._storage = storage

    def handle(self, psop):
        return self._storage.save_psop(psop)


def write_catalog(path, catalog):
    path.write_text(catalog.model_dump_json(), encoding="utf-8")
    return str(path)


def test_legacy_workflow_saves_without_catalog(tmp_path):
    gate = CatalogGate(RecordingHandler(), path_resolver=lambda: None)
    assert gate.handle(make_instance_psop()) == "wf-legacy"


def test_role_workflow_saves_with_approved_catalog(tmp_path):
    path = write_catalog(tmp_path / "catalog.json", approved_catalog())
    storage = WorkflowStorage(str(tmp_path / "store"))
    gate = CatalogGate(StorageHandlerAdapter(storage), path_resolver=lambda: path)
    assert gate.handle(make_role_psop()) == "wf-optimizer-explore"
    assert list((tmp_path / "store" / "workflow_storage" / "psop").glob("*.json"))


def test_unapproved_reference_rejected_and_not_persisted(tmp_path):
    path = write_catalog(tmp_path / "catalog.json", approved_catalog(status="draft"))
    storage = WorkflowStorage(str(tmp_path / "store"))
    gate = CatalogGate(StorageHandlerAdapter(storage), path_resolver=lambda: path)
    with pytest.raises(RoleReferenceError, match="INVALID_ROLE_SKILL"):
        gate.handle(make_role_psop())
    assert list(storage.psop_dir.glob("*.json")) == []


def test_missing_catalog_rejected(tmp_path):
    with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
        ensure_role_references_authorized(make_role_psop(), None)


def test_catalog_version_mismatch_rejected(tmp_path):
    path = write_catalog(tmp_path / "catalog.json", approved_catalog())
    with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
        ensure_role_references_authorized(
            make_role_psop(catalog_version="pilot-v2"), path)


def test_role_reference_error_maps_to_readable_422():
    response = storage_http_exception(RoleReferenceError("INVALID_ROLE_SKILL: t1"))
    assert response.status_code == 422
    assert response.detail == "INVALID_ROLE_SKILL: t1"


def test_persistence_roundtrip_preserves_role_fields(tmp_path):
    catalog = approved_catalog()
    path = write_catalog(tmp_path / "catalog.json", catalog)
    storage = WorkflowStorage(str(tmp_path / "store"))
    original = make_role_psop()

    assert storage.save_psop(original) == original.id
    loaded = storage.load_psop(original.id)

    assert loaded == original
    assert loaded.catalog_version == "pilot-v1"
    task = loaded.steps[0].subtasks[0]
    assert (task.binding, task.agent, task.skill, task.role_version) == (
        "role", "optimizer", "explore", "1")
    catalog.validate_workflow(loaded)


def test_shared_handlers_save_is_gated(monkeypatch, tmp_path):
    recording = RecordingHandler()
    monkeypatch.setattr(
        "orchestrate.core.shared_handlers.get_storage_handler", lambda _: recording)
    monkeypatch.setattr(SharedHandlers, "_save_handle", None)
    try:
        gate = SharedHandlers.save_psop()
        assert isinstance(gate, CatalogGate)

        path = write_catalog(tmp_path / "catalog.json", approved_catalog(status="draft"))
        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path", lambda: path)
        with pytest.raises(RoleReferenceError, match="INVALID_ROLE_SKILL"):
            gate.handle(make_role_psop())
        assert recording.saved == []

        monkeypatch.setattr(
            "orchestrate.core.catalog_gate.configured_catalog_path",
            lambda: write_catalog(tmp_path / "ok.json", approved_catalog()))
        assert gate.handle(make_role_psop()) == "wf-optimizer-explore"
        assert recording.saved == ["wf-optimizer-explore"]
    finally:
        SharedHandlers._save_handle = None


class TestCatalogLoadFailures:
    def test_missing_file_is_catalog_unavailable(self, tmp_path):
        with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
            ensure_role_references_authorized(
                make_role_psop(), str(tmp_path / "absent.json"))

    def test_unreadable_path_is_catalog_unavailable(self, tmp_path):
        # A directory where the release file is expected cannot be opened
        # as text (PermissionError on Windows, IsADirectoryError on POSIX).
        (tmp_path / "catalog.json").mkdir()
        with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
            ensure_role_references_authorized(
                make_role_psop(), str(tmp_path / "catalog.json"))

    def test_corrupt_json_is_catalog_unavailable(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
            ensure_role_references_authorized(make_role_psop(), str(path))

    def test_invalid_catalog_structure_is_catalog_unavailable(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text(
            '{"catalog_version": "pilot-v1", "roles": "not-a-list"}', encoding="utf-8")
        with pytest.raises(RoleReferenceError, match="CATALOG_VERSION_UNAVAILABLE"):
            ensure_role_references_authorized(make_role_psop(), str(path))

    def test_unknown_skill_is_invalid_role_skill(self, tmp_path):
        path = write_catalog(tmp_path / "catalog.json", approved_catalog())
        with pytest.raises(RoleReferenceError, match="INVALID_ROLE_SKILL"):
            ensure_role_references_authorized(
                make_role_psop(skill="unknown"), path)

    def test_load_failure_hides_local_path_and_keeps_cause(self, tmp_path):
        path = tmp_path / "secret-dir" / "absent.json"
        with pytest.raises(RoleReferenceError) as error:
            ensure_role_references_authorized(make_role_psop(), str(path))
        assert "secret-dir" not in str(error.value)
        assert isinstance(error.value.__cause__, OSError)

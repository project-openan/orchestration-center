# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# tests/test_manager.py
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrate.solution_package.manager import SolutionPackageManager


DEMO_PACKAGE = "IG1526A_AN_L4_Wireless_Energy_Efficiency_Optimization_Solution_Package_v1.0.0"


def test_bundled_demo_record_matches_canonical_sample_and_original_pdf():
    """The tracked runtime seed must not diverge from the sample seed from main."""
    root = Path(__file__).resolve().parents[1]
    runtime_seed = root / "data" / "solution_packages" / f"{DEMO_PACKAGE}.json"
    canonical_seed = root / "samples" / "solution_packages" / f"{DEMO_PACKAGE}.json"
    record = json.loads(runtime_seed.read_text(encoding="utf-8"))
    assert record == json.loads(canonical_seed.read_text(encoding="utf-8"))
    assert record["pdf_filename"] == f"{DEMO_PACKAGE}.pdf"
    assert record["chapter_count"] == len(record["chapters"]) == 13
    with runtime_seed.with_suffix(".pdf").open("rb") as pdf:
        assert pdf.read(5) == b"%PDF-"


def test_default_demo_seeding_keeps_custom_storage_empty_and_existing_imports_intact(tmp_path, monkeypatch):
    """Resolve the rebase conflict without dropping main's deployment isolation."""
    from orchestrate.solution_package import manager as manager_module

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(manager_module, "__file__",
                        str(tmp_path / "orchestrate" / "solution_package" / "manager.py"))
    monkeypatch.delenv("TESTING", raising=False)
    seeds = tmp_path / "samples" / "solution_packages"
    seeds.mkdir(parents=True)
    shutil.copyfile(root / "samples" / "solution_packages" / f"{DEMO_PACKAGE}.json",
                    seeds / f"{DEMO_PACKAGE}.json")

    custom = SolutionPackageManager(storage_dir=str(tmp_path / "custom"))
    assert custom.retrieve_all() == []
    default = SolutionPackageManager()
    assert default.storage_dir == tmp_path / "data" / "solution_packages"
    assert default.retrieve_by_filename(f"{DEMO_PACKAGE}.pdf")["chapter_count"] == 13

    existing = default.storage_dir / f"{DEMO_PACKAGE}.json"
    existing.write_text('{"pdf_filename":"operator.pdf","chapters":{}}', encoding="utf-8")
    SolutionPackageManager()
    assert json.loads(existing.read_text(encoding="utf-8"))["pdf_filename"] == "operator.pdf"


def test_default_seeding_tops_up_new_packages_without_overwriting_existing(tmp_path, monkeypatch):
    """An existing deployment gains newly shipped default packages on restart,
    while user-imported or previously seeded records stay untouched."""
    from orchestrate.solution_package import manager as manager_module

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(manager_module, "__file__",
                        str(tmp_path / "orchestrate" / "solution_package" / "manager.py"))
    monkeypatch.delenv("TESTING", raising=False)
    seeds = tmp_path / "samples" / "solution_packages"
    seeds.mkdir(parents=True)
    shutil.copyfile(root / "samples" / "solution_packages" / f"{DEMO_PACKAGE}.json",
                    seeds / f"{DEMO_PACKAGE}.json")

    # first deployment generation: only the demo package ships as a seed
    first = SolutionPackageManager()
    assert first.retrieve_by_filename(f"{DEMO_PACKAGE}.pdf")["chapter_count"] == 13

    # simulate an operator edit to the seeded demo record
    demo = first.storage_dir / f"{DEMO_PACKAGE}.json"
    record = json.loads(demo.read_text(encoding="utf-8"))
    record["workflow_id"] = "operator-changed"
    demo.write_text(json.dumps(record), encoding="utf-8")

    # a later release ships one more default package
    (seeds / "IG1501_new_default.json").write_text(json.dumps({
        "pdf_filename": "IG1501_new_default.pdf",
        "chapters": {"5. Interaction Flow": "steps"},
        "chapter_count": 1,
        "chapter_titles": ["5. Interaction Flow"],
        "created_at": "2026-10-15T08:00:00+00:00",
        "workflow_id": "shipped-seed-id",
    }), encoding="utf-8")

    # re-initialization must add the new package without reverting the edit
    SolutionPackageManager()
    assert first.retrieve_by_filename("IG1501_new_default.pdf")["workflow_id"] == "shipped-seed-id"
    kept = json.loads(demo.read_text(encoding="utf-8"))
    assert kept["workflow_id"] == "operator-changed"
    assert kept["chapter_count"] == 13


def test_testing_mode_disables_default_demo_copy(tmp_path, monkeypatch):
    from orchestrate.solution_package import manager as manager_module

    monkeypatch.setattr(manager_module, "__file__",
                        str(tmp_path / "orchestrate" / "solution_package" / "manager.py"))
    monkeypatch.setenv("TESTING", "true")
    seeds = tmp_path / "samples" / "solution_packages"
    seeds.mkdir(parents=True)
    (seeds / "demo.json").write_text("{}", encoding="utf-8")
    assert SolutionPackageManager().retrieve_all() == []


@pytest.fixture
def temp_storage_dir():
    """Create temporary storage directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def manager(temp_storage_dir):
    """Create manager instance"""
    return SolutionPackageManager(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_chapters():
    """Sample chapter data"""
    return {
        "Chapter 1": "This is the content of chapter 1",
        "Chapter 2": "This is the content of chapter 2, containing keyword test",
        "Chapter 3": "This is chapter 3"
    }


class TestSolutionPackageManagerInit:
    """Test initialization method"""

    def test_init_with_default_path(self, tmp_path, monkeypatch):
        from orchestrate.solution_package import manager as module
        monkeypatch.setattr(module, "__file__", str(tmp_path / "orchestrate/solution_package/manager.py"))
        monkeypatch.setenv("TESTING", "true")
        manager = SolutionPackageManager()
        assert manager.storage_dir == tmp_path / "data/solution_packages"

    def test_init_with_custom_path(self, temp_storage_dir):
        """Test using custom storage path"""
        manager = SolutionPackageManager(storage_dir=temp_storage_dir)
        assert manager.storage_dir == Path(temp_storage_dir)
        assert manager.storage_dir.exists()


class TestGetStoragePath:
    """Test _get_storage_path method"""

    def test_get_storage_path_with_extension(self, manager):
        """Test filename with extension"""
        result = manager._get_storage_path("document.pdf")
        assert result == manager.storage_dir / "document.json"

    def test_get_storage_path_without_extension(self, manager):
        """Test filename without extension"""
        result = manager._get_storage_path("document")
        assert result == manager.storage_dir / "document.json"

    def test_get_storage_path_nested_path(self, manager):
        """Test filename with nested path"""
        from orchestrate.persistence.errors import StorageValidationError
        with pytest.raises(StorageValidationError):
            manager._get_storage_path("/path/to/file.pdf")


class TestStoreSolutionPackage:
    """Test store_solution_package method"""

    def test_store_success(self, manager, sample_chapters):
        """Test successful storage"""
        pdf_name = "test.pdf"
        result = manager.store_solution_package(pdf_name, sample_chapters)

        assert result is True
        storage_file = manager.storage_dir / "test.json"
        assert storage_file.exists()

        with open(storage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert data["pdf_filename"] == pdf_name
        assert data["chapters"] == sample_chapters
        assert data["chapter_count"] == 3
        assert data["chapter_titles"] == list(sample_chapters.keys())

    def test_store_write_error(self, manager, sample_chapters):
        """Test error when writing file"""
        from orchestrate.persistence.errors import StorageUnavailableError
        with patch.object(manager.documents._state, "apply", side_effect=OSError("Disk unavailable")):
            with pytest.raises(StorageUnavailableError):
                manager.store_solution_package("test.pdf", sample_chapters)

    def test_store_overwrite_existing(self, manager, sample_chapters):
        """Test overwriting existing file"""
        # Store once
        manager.store_solution_package("test.pdf", sample_chapters)
        # Store again with modified data
        new_chapters = {"New Chapter": "New content"}
        manager.store_solution_package("test.pdf", new_chapters)

        storage_file = manager.storage_dir / "test.json"
        with open(storage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert data["chapters"] == new_chapters
        assert data["chapter_count"] == 1

    def test_reparse_keeps_generated_workflow_links(self, manager, sample_chapters):
        """Re-parsing a package must not drop workflows generated earlier"""
        manager.store_solution_package("test.pdf", sample_chapters)
        assert manager.link_workflow("test.pdf", "wf-role", "role") is True

        manager.store_solution_package("test.pdf", {"New Chapter": "New content"})
        data = manager.retrieve_by_filename("test.pdf")

        assert data["chapters"] == {"New Chapter": "New content"}
        assert data["workflow_id"] == "wf-role"
        assert data["workflow_bindings"] == {"role": "wf-role"}


class TestRetrieveByFilename:
    """Test retrieve_by_filename method"""

    def test_retrieve_existing(self, manager, sample_chapters):
        """Test retrieving existing data"""
        manager.store_solution_package("test.pdf", sample_chapters)
        result = manager.retrieve_by_filename("test.pdf")

        assert result is not None
        assert result["pdf_filename"] == "test.pdf"
        assert result["chapters"] == sample_chapters

    def test_retrieve_nonexistent(self, manager):
        """Test retrieving non-existent data"""
        result = manager.retrieve_by_filename("nonexistent.pdf")
        assert result is None

    def test_retrieve_read_error(self, manager, sample_chapters):
        """Test error when reading file"""
        manager.store_solution_package("test.pdf", sample_chapters)

        from orchestrate.persistence.errors import StorageCorruptionError
        (manager.storage_dir / "test.json").write_text("{ broken", encoding="utf-8")
        with pytest.raises(StorageCorruptionError):
            manager.retrieve_by_filename("test.pdf")


class TestRetrieveAll:
    """Test retrieve_all method"""

    def test_retrieve_all_empty(self, manager):
        """Test empty storage directory"""
        result = manager.retrieve_all()
        assert result == []

    def test_retrieve_all_with_data(self, manager, sample_chapters):
        """Test retrieving all data"""
        manager.store_solution_package("test1.pdf", sample_chapters)
        manager.store_solution_package("test2.pdf", {"Ch1": "content"})

        result = manager.retrieve_all()
        assert len(result) == 2
        filenames = [r["pdf_filename"] for r in result]
        assert "test1.pdf" in filenames
        assert "test2.pdf" in filenames

    def test_retrieve_all_skip_corrupted(self, manager, sample_chapters):
        """Test skipping corrupted files"""
        manager.store_solution_package("test.pdf", sample_chapters)
        # Create a corrupted JSON file
        corrupted = manager.storage_dir / "corrupted.json"
        corrupted.write_text("{ invalid json }")

        from orchestrate.persistence.errors import StorageCorruptionError
        with pytest.raises(StorageCorruptionError):
            manager.retrieve_all()


class TestGetAllFilenames:
    """Test get_all_filenames method"""

    def test_get_filenames_empty(self, manager):
        """Test empty storage directory"""
        result = manager.get_all_filenames()
        assert result == []

    def test_get_filenames_with_data(self, manager, sample_chapters):
        """Test getting filename list"""
        manager.store_solution_package("doc1.pdf", sample_chapters)
        manager.store_solution_package("doc2.pdf", {"Ch": "content"})

        result = manager.get_all_filenames()
        assert set(result) == {"doc1.pdf", "doc2.pdf"}


class TestDeleteByFilename:
    """Test delete_by_filename method"""

    def test_delete_existing(self, manager, sample_chapters):
        """Test deleting existing file"""
        manager.store_solution_package("test.pdf", sample_chapters)
        storage_file = manager.storage_dir / "test.json"
        assert storage_file.exists()

        result = manager.delete_by_filename("test.pdf")
        assert result is True
        assert not storage_file.exists()

    def test_delete_nonexistent(self, manager):
        """Test deleting non-existent file"""
        result = manager.delete_by_filename("nonexistent.pdf")
        assert result is False


class TestGetChapterContent:
    """Test get_chapter_content method"""

    def test_get_existing_chapter(self, manager, sample_chapters):
        """Test getting existing chapter"""
        manager.store_solution_package("test.pdf", sample_chapters)
        content = manager.get_chapter_content("test.pdf", "Chapter 1")
        assert content == "This is the content of chapter 1"

    def test_get_nonexistent_chapter(self, manager, sample_chapters):
        """Test getting non-existent chapter"""
        manager.store_solution_package("test.pdf", sample_chapters)
        content = manager.get_chapter_content("test.pdf", "Nonexistent")
        assert content is None

    def test_get_nonexistent_file(self, manager):
        """Test getting chapter from non-existent file"""
        content = manager.get_chapter_content("nonexistent.pdf", "Chapter 1")
        assert content is None


class TestLinkWorkflow:
    """Test link_workflow method"""

    def test_link_unknown_package(self, manager):
        """Linking a package that was never stored fails"""
        assert manager.link_workflow("missing.pdf", "wf-1") is False

    def test_link_records_latest_and_binding_slot(self, manager, sample_chapters):
        """A link updates workflow_id and its own binding slot"""
        manager.store_solution_package("test.pdf", sample_chapters)

        assert manager.link_workflow("test.pdf", "wf-instance", "instance") is True

        data = manager.retrieve_by_filename("test.pdf")
        assert data["workflow_id"] == "wf-instance"
        assert data["workflow_bindings"] == {"instance": "wf-instance"}

    def test_role_link_does_not_overwrite_instance_link(self, manager, sample_chapters):
        """Role and instance generations of one package coexist"""
        manager.store_solution_package("test.pdf", sample_chapters)

        assert manager.link_workflow("test.pdf", "wf-instance", "instance") is True
        assert manager.link_workflow("test.pdf", "wf-role", "role") is True

        data = manager.retrieve_by_filename("test.pdf")
        assert data["workflow_bindings"]["instance"] == "wf-instance"
        assert data["workflow_bindings"]["role"] == "wf-role"
        assert data["workflow_id"] == "wf-role"

    def test_relink_same_binding_replaces_only_that_slot(self, manager, sample_chapters):
        """Regenerating one binding keeps the other binding's workflow"""
        manager.store_solution_package("test.pdf", sample_chapters)
        manager.link_workflow("test.pdf", "wf-role-1", "role")
        manager.link_workflow("test.pdf", "wf-instance", "instance")

        assert manager.link_workflow("test.pdf", "wf-role-2", "role") is True

        data = manager.retrieve_by_filename("test.pdf")
        assert data["workflow_bindings"] == {"role": "wf-role-2", "instance": "wf-instance"}
        assert data["workflow_id"] == "wf-role-2"

    def test_invalid_binding_is_rejected_without_write(self, manager, sample_chapters):
        """Unknown bindings must not corrupt the stored record"""
        manager.store_solution_package("test.pdf", sample_chapters)

        assert manager.link_workflow("test.pdf", "wf-x", "catalog") is False

        data = manager.retrieve_by_filename("test.pdf")
        assert "workflow_id" not in data
        assert "workflow_bindings" not in data


class TestSearchChaptersByKeyword:
    """Test search_chapters_by_keyword method"""

    def test_search_found(self, manager, sample_chapters):
        """Test search found results"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results = manager.search_chapters_by_keyword("test")

        assert len(results) == 1
        assert results[0]["pdf_filename"] == "test.pdf"
        assert "Chapter 2" in results[0]["matching_chapters"]

    def test_search_not_found(self, manager, sample_chapters):
        """Test search no results"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results = manager.search_chapters_by_keyword("nonexistent")
        assert results == []

    def test_search_case_insensitive(self, manager, sample_chapters):
        """Test search is case insensitive"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results_lower = manager.search_chapters_by_keyword("test")
        results_upper = manager.search_chapters_by_keyword("TEST")

        assert len(results_lower) == len(results_upper) == 1


class TestGetStorageStats:
    """Test get_storage_stats method"""

    def test_stats_empty(self, manager):
        """Test stats for empty storage"""
        stats = manager.get_storage_stats()

        assert stats["storage_directory"] == str(manager.storage_dir)
        assert stats["total_packages"] == 0
        assert stats["total_chapters"] == 0
        assert stats["package_filenames"] == []

    def test_stats_with_data(self, manager, sample_chapters):
        """Test stats with data"""
        manager.store_solution_package("test1.pdf", sample_chapters)
        manager.store_solution_package("test2.pdf", {"Ch1": "c1", "Ch2": "c2"})

        stats = manager.get_storage_stats()

        assert stats["total_packages"] == 2
        assert stats["total_chapters"] == 5  # 3 + 2
        assert set(stats["package_filenames"]) == {"test1.pdf", "test2.pdf"}

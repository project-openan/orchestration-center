# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

    @patch('orchestrate.solution_package.manager.Path')
    def test_init_with_default_path(self, mock_path_class):
        """Test using default storage path"""
        mock_current_file = MagicMock(spec=Path)
        mock_framework_dir = MagicMock(spec=Path)
        mock_project_root = MagicMock(spec=Path)

        # Set up path relationship: current_file.parent.parent = project_root
        mock_current_file.parent.parent = mock_project_root
        mock_path_class.return_value.resolve.return_value = mock_current_file

        # Set up the constructed storage_dir
        expected_storage = mock_project_root / "data" / "solution_packages"

        # Instantiate manager
        manager = SolutionPackageManager()

        # Assertions
        assert manager.storage_dir == expected_storage
        # Verify directory was created
        expected_storage.mkdir.assert_called_once_with(parents=True, exist_ok=True)


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
        result = manager._get_storage_path("/path/to/file.pdf")
        assert result == manager.storage_dir / "file.json"


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
        with patch('builtins.open', side_effect=IOError("Write error")):
            result = manager.store_solution_package("test.pdf", sample_chapters)
            assert result is False

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

    def test_retrieve_read_error(self, manager):
        """Test error when reading file"""
        manager.store_solution_package("test.pdf", sample_chapters)

        with patch('builtins.open', side_effect=IOError("Read error")):
            result = manager.retrieve_by_filename("test.pdf")
            assert result is None


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

        result = manager.retrieve_all()
        # Should only return valid files
        assert len(result) == 1
        assert result[0]["pdf_filename"] == "test.pdf"


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

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
    """创建临时存储目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def manager(temp_storage_dir):
    """创建管理器实例"""
    return SolutionPackageManager(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_chapters():
    """示例章节数据"""
    return {
        "Chapter 1": "这是第一章的内容",
        "Chapter 2": "这是第二章的内容，包含关键词 test",
        "Chapter 3": "这是第三章"
    }


class TestSolutionPackageManagerInit:
    """测试初始化方法"""

    @patch('orchestrate.solution_package.manager.Path')
    def test_init_with_default_path(self, mock_path_class):
        """测试使用默认存储路径"""
        mock_current_file = MagicMock(spec=Path)
        mock_framework_dir = MagicMock(spec=Path)
        mock_project_root = MagicMock(spec=Path)

        # 设置路径关系: current_file.parent.parent = project_root
        mock_current_file.parent.parent = mock_project_root
        mock_path_class.return_value.resolve.return_value = mock_current_file

        # 设置 storage_dir 的构建结果
        expected_storage = mock_project_root / "data" / "solution_packages"

        # 实例化管理器
        manager = SolutionPackageManager()

        # 断言
        assert manager.storage_dir == expected_storage
        # 验证创建了目录
        expected_storage.mkdir.assert_called_once_with(parents=True, exist_ok=True)


    def test_init_with_custom_path(self, temp_storage_dir):
        """测试使用自定义存储路径"""
        manager = SolutionPackageManager(storage_dir=temp_storage_dir)
        assert manager.storage_dir == Path(temp_storage_dir)
        assert manager.storage_dir.exists()


class TestGetStoragePath:
    """测试 _get_storage_path 方法"""

    def test_get_storage_path_with_extension(self, manager):
        """测试带扩展名的文件名"""
        result = manager._get_storage_path("document.pdf")
        assert result == manager.storage_dir / "document.json"

    def test_get_storage_path_without_extension(self, manager):
        """测试不带扩展名的文件名"""
        result = manager._get_storage_path("document")
        assert result == manager.storage_dir / "document.json"

    def test_get_storage_path_nested_path(self, manager):
        """测试嵌套路径的文件名"""
        result = manager._get_storage_path("/path/to/file.pdf")
        assert result == manager.storage_dir / "file.json"


class TestStoreSolutionPackage:
    """测试 store_solution_package 方法"""

    def test_store_success(self, manager, sample_chapters):
        """测试成功存储"""
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
        """测试写入文件时出错"""
        with patch('builtins.open', side_effect=IOError("Write error")):
            result = manager.store_solution_package("test.pdf", sample_chapters)
            assert result is False

    def test_store_overwrite_existing(self, manager, sample_chapters):
        """测试覆盖已存在的文件"""
        # 先存储一次
        manager.store_solution_package("test.pdf", sample_chapters)
        # 修改数据后再次存储
        new_chapters = {"New Chapter": "新内容"}
        manager.store_solution_package("test.pdf", new_chapters)

        storage_file = manager.storage_dir / "test.json"
        with open(storage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert data["chapters"] == new_chapters
        assert data["chapter_count"] == 1


class TestRetrieveByFilename:
    """测试 retrieve_by_filename 方法"""

    def test_retrieve_existing(self, manager, sample_chapters):
        """测试检索已存在的数据"""
        manager.store_solution_package("test.pdf", sample_chapters)
        result = manager.retrieve_by_filename("test.pdf")

        assert result is not None
        assert result["pdf_filename"] == "test.pdf"
        assert result["chapters"] == sample_chapters

    def test_retrieve_nonexistent(self, manager):
        """测试检索不存在的数据"""
        result = manager.retrieve_by_filename("nonexistent.pdf")
        assert result is None

    def test_retrieve_read_error(self, manager):
        """测试读取文件时出错"""
        manager.store_solution_package("test.pdf", sample_chapters)

        with patch('builtins.open', side_effect=IOError("Read error")):
            result = manager.retrieve_by_filename("test.pdf")
            assert result is None


class TestRetrieveAll:
    """测试 retrieve_all 方法"""

    def test_retrieve_all_empty(self, manager):
        """测试空存储目录"""
        result = manager.retrieve_all()
        assert result == []

    def test_retrieve_all_with_data(self, manager, sample_chapters):
        """测试检索所有数据"""
        manager.store_solution_package("test1.pdf", sample_chapters)
        manager.store_solution_package("test2.pdf", {"Ch1": "content"})

        result = manager.retrieve_all()
        assert len(result) == 2
        filenames = [r["pdf_filename"] for r in result]
        assert "test1.pdf" in filenames
        assert "test2.pdf" in filenames

    def test_retrieve_all_skip_corrupted(self, manager, sample_chapters):
        """测试跳过损坏的文件"""
        manager.store_solution_package("test.pdf", sample_chapters)
        # 创建一个损坏的JSON文件
        corrupted = manager.storage_dir / "corrupted.json"
        corrupted.write_text("{ invalid json }")

        result = manager.retrieve_all()
        # 应该只返回有效的文件
        assert len(result) == 1
        assert result[0]["pdf_filename"] == "test.pdf"


class TestGetAllFilenames:
    """测试 get_all_filenames 方法"""

    def test_get_filenames_empty(self, manager):
        """测试空存储目录"""
        result = manager.get_all_filenames()
        assert result == []

    def test_get_filenames_with_data(self, manager, sample_chapters):
        """测试获取文件名列表"""
        manager.store_solution_package("doc1.pdf", sample_chapters)
        manager.store_solution_package("doc2.pdf", {"Ch": "content"})

        result = manager.get_all_filenames()
        assert set(result) == {"doc1.pdf", "doc2.pdf"}


class TestDeleteByFilename:
    """测试 delete_by_filename 方法"""

    def test_delete_existing(self, manager, sample_chapters):
        """测试删除已存在的文件"""
        manager.store_solution_package("test.pdf", sample_chapters)
        storage_file = manager.storage_dir / "test.json"
        assert storage_file.exists()

        result = manager.delete_by_filename("test.pdf")
        assert result is True
        assert not storage_file.exists()

    def test_delete_nonexistent(self, manager):
        """测试删除不存在的文件"""
        result = manager.delete_by_filename("nonexistent.pdf")
        assert result is False


class TestGetChapterContent:
    """测试 get_chapter_content 方法"""

    def test_get_existing_chapter(self, manager, sample_chapters):
        """测试获取已存在的章节"""
        manager.store_solution_package("test.pdf", sample_chapters)
        content = manager.get_chapter_content("test.pdf", "Chapter 1")
        assert content == "这是第一章的内容"

    def test_get_nonexistent_chapter(self, manager, sample_chapters):
        """测试获取不存在的章节"""
        manager.store_solution_package("test.pdf", sample_chapters)
        content = manager.get_chapter_content("test.pdf", "Nonexistent")
        assert content is None

    def test_get_nonexistent_file(self, manager):
        """测试获取不存在文件的章节"""
        content = manager.get_chapter_content("nonexistent.pdf", "Chapter 1")
        assert content is None


class TestSearchChaptersByKeyword:
    """测试 search_chapters_by_keyword 方法"""

    def test_search_found(self, manager, sample_chapters):
        """测试搜索到结果"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results = manager.search_chapters_by_keyword("test")

        assert len(results) == 1
        assert results[0]["pdf_filename"] == "test.pdf"
        assert "Chapter 2" in results[0]["matching_chapters"]

    def test_search_not_found(self, manager, sample_chapters):
        """测试未搜索到结果"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results = manager.search_chapters_by_keyword("nonexistent")
        assert results == []

    def test_search_case_insensitive(self, manager, sample_chapters):
        """测试搜索不区分大小写"""
        manager.store_solution_package("test.pdf", sample_chapters)
        results_lower = manager.search_chapters_by_keyword("test")
        results_upper = manager.search_chapters_by_keyword("TEST")

        assert len(results_lower) == len(results_upper) == 1


class TestGetStorageStats:
    """测试 get_storage_stats 方法"""

    def test_stats_empty(self, manager):
        """测试空存储的统计信息"""
        stats = manager.get_storage_stats()

        assert stats["storage_directory"] == str(manager.storage_dir)
        assert stats["total_packages"] == 0
        assert stats["total_chapters"] == 0
        assert stats["package_filenames"] == []

    def test_stats_with_data(self, manager, sample_chapters):
        """测试有数据时的统计信息"""
        manager.store_solution_package("test1.pdf", sample_chapters)
        manager.store_solution_package("test2.pdf", {"Ch1": "c1", "Ch2": "c2"})

        stats = manager.get_storage_stats()

        assert stats["total_packages"] == 2
        assert stats["total_chapters"] == 5  # 3 + 2
        assert set(stats["package_filenames"]) == {"test1.pdf", "test2.pdf"}

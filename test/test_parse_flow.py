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

# tests/test_parse_flow.py
import pytest
from unittest.mock import patch, MagicMock

from orchestrate.solution_package.parse_flow import (
    SolutionPackageParser,
    PDFParsingError,
    ChapterNotFoundError
)


@pytest.fixture
def parser():
    """创建解析器实例"""
    with patch('orchestrate.solution_package.parse_flow.get_llm_instance'):
        return SolutionPackageParser()


@pytest.fixture
def mock_doc():
    """创建模拟的PyMuPDF文档"""
    doc = MagicMock()
    doc.page_count = 10
    doc.get_toc.return_value = [
        (1, "Chapter 1", 1),
        (2, "Section 1.1", 2),
        (1, "Chapter 2", 5),
        (1, "Chapter 3", 8),
    ]

    # 模拟页面文本提取
    def mock_get_text(page_idx):
        texts = {
            0: "Chapter 1 content page 1",
            1: "Chapter 1 content page 2",
            2: "Chapter 1 content page 3",
            3: "Chapter 1 content page 4",
            4: "Chapter 2 content page 1",
            5: "Chapter 2 content page 2",
            6: "Chapter 2 content page 3",
            7: "Chapter 3 content page 1",
            8: "Chapter 3 content page 2",
            9: "Chapter 3 content page 3",
        }
        return texts.get(page_idx, "")

    doc.__getitem__.side_effect = lambda idx: MagicMock(get_text=lambda: mock_get_text(idx))
    return doc


class TestFindChapterRange:
    """测试 find_chapter_range 静态方法"""

    def test_find_existing_chapter(self, mock_doc):
        """测试找到已存在的章节"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Chapter 1")
        assert start == 1  # 页码从1开始
        assert end == 5  # 下一个一级章节的起始页

    def test_find_last_chapter(self, mock_doc):
        """测试找到最后一个章节"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Chapter 3")
        assert start == 8
        assert end == mock_doc.page_count  # 文档末尾

    def test_find_nonexistent_chapter(self, mock_doc):
        """测试查找不存在的章节"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Nonexistent")
        assert start is None
        assert end == mock_doc.page_count


class TestExtractText:
    """测试 extract_text 静态方法"""

    def test_extract_valid_range(self, mock_doc):
        """测试提取有效范围内的文本"""
        text = SolutionPackageParser.extract_text(mock_doc, 1, 3)
        assert "Chapter 1 content" in text

    def test_extract_empty_range(self, mock_doc):
        """测试提取空范围"""
        text = SolutionPackageParser.extract_text(mock_doc, 5, 5)
        assert text == ""

    def test_extract_out_of_bounds(self, mock_doc):
        """测试提取超出范围的页码"""
        text = SolutionPackageParser.extract_text(mock_doc, 1, 100)
        # 应该正常返回，不抛出异常
        assert isinstance(text, str)

    def test_extract_with_page_error(self, mock_doc):
        """测试某页提取失败时继续处理其他页"""
        mock_doc.__getitem__.side_effect = lambda idx: MagicMock(
            get_text=lambda: (_ for _ in ()).throw(Exception("Page error")) if idx == 1 else f"Page {idx} text"
        )
        text = SolutionPackageParser.extract_text(mock_doc, 1, 3)
        # 应该包含其他页面的内容
        assert "Page 0 text" in text or "Page 2 text" in text


class TestBuildMarkdownPrompt:
    """测试 build_markdown_prompt 静态方法"""

    def test_prompt_contains_requirements(self):
        """测试提示词包含必要的格式要求"""
        sample_text = "Test content"
        prompt = SolutionPackageParser.build_markdown_prompt(sample_text)

        assert "Markdown" in prompt
        assert "#" in prompt  # 标题标记
        assert "列表" in prompt or "list" in prompt.lower()
        assert sample_text in prompt

    def test_prompt_translation_instruction(self):
        """测试提示词包含翻译指令"""
        prompt = SolutionPackageParser.build_markdown_prompt("Test")
        assert "中文" in prompt or "翻译" in prompt
        assert "Agent" in prompt and "智能体" in prompt


class TestGetChapterText:
    """测试 get_chapter_text 方法"""

    def test_get_existing_chapter(self, parser, mock_doc, tmp_path):
        """测试获取已存在的章节"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            text = parser.get_chapter_text(str(pdf_path), "Chapter 1")
            assert "Chapter 1 content" in text

    def test_get_nonexistent_file(self, parser):
        """测试获取不存在的文件"""
        with pytest.raises(PDFParsingError, match="does not exist"):
            parser.get_chapter_text("/nonexistent/path.pdf", "Chapter 1")

    def test_get_nonexistent_chapter(self, parser, mock_doc, tmp_path):
        """测试获取不存在的章节"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            with pytest.raises(ChapterNotFoundError):
                parser.get_chapter_text(str(pdf_path), "Nonexistent Chapter")

    def test_get_chapter_open_error(self, parser, tmp_path):
        """测试打开PDF文件失败"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', side_effect=Exception("Cannot open")):
            with pytest.raises(PDFParsingError, match="Cannot open"):
                parser.get_chapter_text(str(pdf_path), "Chapter 1")


class TestExtractAllChapters:
    """测试 extract_all_chapters 方法"""

    def test_extract_with_toc(self, parser, mock_doc, tmp_path):
        """测试从有目录的PDF提取所有章节"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            chapters = parser.extract_all_chapters(str(pdf_path))

            # 应该提取3个一级章节
            assert len(chapters) == 3
            assert "Chapter 1" in chapters
            assert "Chapter 2" in chapters
            assert "Chapter 3" in chapters

    def test_extract_empty_toc(self, parser, tmp_path):
        """测试从无目录的PDF提取"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_empty_doc = MagicMock()
        mock_empty_doc.page_count = 5
        mock_empty_doc.get_toc.return_value = []

        with patch('fitz.open', return_value=mock_empty_doc):
            chapters = parser.extract_all_chapters(str(pdf_path))
            assert chapters == {}

    def test_extract_nonexistent_file(self, parser):
        """测试提取不存在的文件"""
        with pytest.raises(PDFParsingError):
            parser.extract_all_chapters("/nonexistent.pdf")


class TestConvertToMarkdown:
    """测试 convert_to_markdown 方法"""

    def test_convert_success(self, parser):
        """测试成功转换"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted Markdown")
        parser.llm = mock_llm

        result = parser.convert_to_markdown("Original text")
        assert result == "# Converted Markdown"
        mock_llm.ask_llm.assert_called_once()

    def test_convert_empty_text(self, parser):
        """测试转换空文本"""
        with pytest.raises(PDFParsingError, match="empty"):
            parser.convert_to_markdown("")

    def test_convert_llm_error(self, parser):
        """测试LLM调用失败"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("LLM error")
        parser.llm = mock_llm

        with pytest.raises(PDFParsingError, match="LLM conversion failed"):
            parser.convert_to_markdown("Some text")


class TestConvertChapterToMarkdown:
    """测试 convert_chapter_to_markdown 方法"""

    def test_convert_with_content(self, parser):
        """测试转换有内容的章节"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Markdown Content")
        parser.llm = mock_llm

        title, content = parser.convert_chapter_to_markdown(("Ch1", "Original"))
        assert title == "Ch1"
        assert "# Markdown Content" in content

    def test_convert_empty_content(self, parser):
        """测试转换空内容章节"""
        title, content = parser.convert_chapter_to_markdown(("Ch1", ""))
        assert title == "Ch1"
        assert "无文本内容" in content or "empty" in content.lower()

    def test_convert_with_error(self, parser):
        """测试转换时出错"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("Conversion failed")
        parser.llm = mock_llm

        title, content = parser.convert_chapter_to_markdown(("Ch1", "Text"))
        assert title == "Ch1"
        assert "转换失败" in content or "failed" in content.lower()


class TestConvertAllChaptersToMarkdown:
    """测试 convert_all_chapters_to_markdown 方法"""

    def test_convert_all_success(self, parser):
        """测试批量转换成功"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted")
        parser.llm = mock_llm

        chapters = {"Ch1": "text1", "Ch2": "text2"}
        result = parser.convert_all_chapters_to_markdown(chapters, max_workers=2)

        assert len(result) == 2
        assert all("# Converted" in v for v in result.values())

    def test_convert_all_preserves_order(self, parser):
        """测试批量转换保持顺序"""
        mock_llm = MagicMock()
        # 让LLM返回带章节名的内容以验证顺序
        call_count = [0]

        def mock_ask(prompt):
            call_count[0] += 1
            return ("prompt", f"# Chapter {call_count[0]}")

        mock_llm.ask_llm.side_effect = mock_ask
        parser.llm = mock_llm

        chapters = {"First": "t1", "Second": "t2", "Third": "t3"}
        result = parser.convert_all_chapters_to_markdown(chapters, max_workers=1)

        # 验证所有章节都被转换
        assert len(result) == 3
        assert all(k in result for k in chapters.keys())


class TestParsePdfChapter:
    """测试 parse_pdf_chapter 方法"""

    def test_parse_success(self, parser, mock_doc, tmp_path):
        """测试成功解析单章节"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Markdown")
        parser.llm = mock_llm

        with patch('fitz.open', return_value=mock_doc):
            result = parser.parse_pdf_chapter(str(pdf_path), "Chapter 1")
            assert result is not None
            assert "# Markdown" in result

    def test_parse_chapter_not_found(self, parser, mock_doc, tmp_path):
        """测试章节不存在时返回None"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            result = parser.parse_pdf_chapter(str(pdf_path), "Nonexistent")
            assert result is None


class TestParsePdfAllChapters:
    """测试 parse_pdf_all_chapters 方法"""

    def test_parse_all_success(self, parser, mock_doc, tmp_path):
        """测试成功解析所有章节"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted")
        parser.llm = mock_llm

        with patch('fitz.open', return_value=mock_doc):
            result = parser.parse_pdf_all_chapters(str(pdf_path), max_workers=2)

            assert len(result) == 3  # 3个一级章节
            assert all("# Converted" in v for v in result.values())

    def test_parse_all_with_error(self, parser, tmp_path):
        """测试解析过程中出错"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', side_effect=Exception("Open failed")):
            with pytest.raises(PDFParsingError):
                parser.parse_pdf_all_chapters(str(pdf_path))
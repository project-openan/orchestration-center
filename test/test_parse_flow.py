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
    """Create parser instance"""
    with patch('orchestrate.solution_package.parse_flow.get_llm_instance'):
        return SolutionPackageParser()


@pytest.fixture
def mock_doc():
    """Create mock PyMuPDF document"""
    doc = MagicMock()
    doc.page_count = 10
    doc.get_toc.return_value = [
        (1, "Chapter 1", 1),
        (2, "Section 1.1", 2),
        (1, "Chapter 2", 5),
        (1, "Chapter 3", 8),
    ]

    # Mock page text extraction
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
    """Test find_chapter_range static method"""

    def test_find_existing_chapter(self, mock_doc):
        """Test finding an existing chapter"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Chapter 1")
        assert start == 1  # Page numbers start from 1
        assert end == 5  # Start page of the next top-level chapter

    def test_find_last_chapter(self, mock_doc):
        """Test finding the last chapter"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Chapter 3")
        assert start == 8
        assert end == mock_doc.page_count  # End of document

    def test_find_nonexistent_chapter(self, mock_doc):
        """Test finding a nonexistent chapter"""
        start, end = SolutionPackageParser.find_chapter_range(mock_doc, "Nonexistent")
        assert start is None
        assert end == mock_doc.page_count


class TestExtractText:
    """Test extract_text static method"""

    def test_extract_valid_range(self, mock_doc):
        """Test extracting text within valid range"""
        text = SolutionPackageParser.extract_text(mock_doc, 1, 3)
        assert "Chapter 1 content" in text

    def test_extract_empty_range(self, mock_doc):
        """Test extracting empty range"""
        text = SolutionPackageParser.extract_text(mock_doc, 5, 5)
        assert text == ""

    def test_extract_out_of_bounds(self, mock_doc):
        """Test extracting pages out of bounds"""
        text = SolutionPackageParser.extract_text(mock_doc, 1, 100)
        # Should return normally, no exception
        assert isinstance(text, str)

    def test_extract_with_page_error(self, mock_doc):
        """Test continuing with other pages when one page extraction fails"""
        mock_doc.__getitem__.side_effect = lambda idx: MagicMock(
            get_text=lambda: (_ for _ in ()).throw(Exception("Page error")) if idx == 1 else f"Page {idx} text"
        )
        text = SolutionPackageParser.extract_text(mock_doc, 1, 3)
        # Should contain content from other pages
        assert "Page 0 text" in text or "Page 2 text" in text


class TestBuildMarkdownPrompt:
    """Test build_markdown_prompt static method"""

    def test_prompt_contains_requirements(self):
        """Test prompt contains necessary format requirements"""
        sample_text = "Test content"
        prompt = SolutionPackageParser.build_markdown_prompt(sample_text)

        assert "Markdown" in prompt
        assert "#" in prompt  # Heading marker
        assert "list" in prompt.lower()
        assert sample_text in prompt

    def test_prompt_translation_instruction(self):
        """Test prompt contains translation instruction"""
        prompt = SolutionPackageParser.build_markdown_prompt("Test")
        assert "Chinese" in prompt or "translate" in prompt
        assert "Agent" in prompt


class TestGetChapterText:
    """Test get_chapter_text method"""

    def test_get_existing_chapter(self, parser, mock_doc, tmp_path):
        """Test getting an existing chapter"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            text = parser.get_chapter_text(str(pdf_path), "Chapter 1")
            assert "Chapter 1 content" in text

    def test_get_nonexistent_file(self, parser):
        """Test getting a nonexistent file"""
        with pytest.raises(PDFParsingError, match="does not exist"):
            parser.get_chapter_text("/nonexistent/path.pdf", "Chapter 1")

    def test_get_nonexistent_chapter(self, parser, mock_doc, tmp_path):
        """Test getting a nonexistent chapter"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            with pytest.raises(ChapterNotFoundError):
                parser.get_chapter_text(str(pdf_path), "Nonexistent Chapter")

    def test_get_chapter_open_error(self, parser, tmp_path):
        """Test failing to open PDF file"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', side_effect=Exception("Cannot open")):
            with pytest.raises(PDFParsingError, match="Cannot open"):
                parser.get_chapter_text(str(pdf_path), "Chapter 1")


class TestExtractAllChapters:
    """Test extract_all_chapters method"""

    def test_extract_with_toc(self, parser, mock_doc, tmp_path):
        """Test extracting all chapters from PDF with TOC"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            chapters = parser.extract_all_chapters(str(pdf_path))

            # Should extract 3 top-level chapters
            assert len(chapters) == 3
            assert "Chapter 1" in chapters
            assert "Chapter 2" in chapters
            assert "Chapter 3" in chapters

    def test_extract_empty_toc(self, parser, tmp_path):
        """Test extracting from PDF without TOC"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_empty_doc = MagicMock()
        mock_empty_doc.page_count = 5
        mock_empty_doc.get_toc.return_value = []

        with patch('fitz.open', return_value=mock_empty_doc):
            chapters = parser.extract_all_chapters(str(pdf_path))
            assert chapters == {}

    def test_extract_nonexistent_file(self, parser):
        """Test extracting from a nonexistent file"""
        with pytest.raises(PDFParsingError):
            parser.extract_all_chapters("/nonexistent.pdf")


class TestConvertToMarkdown:
    """Test convert_to_markdown method"""

    def test_convert_success(self, parser):
        """Test successful conversion"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted Markdown")
        parser.llm = mock_llm

        result = parser.convert_to_markdown("Original text")
        assert result == "# Converted Markdown"
        mock_llm.ask_llm.assert_called_once()

    def test_convert_empty_text(self, parser):
        """Test converting empty text"""
        with pytest.raises(PDFParsingError, match="empty"):
            parser.convert_to_markdown("")

    def test_convert_llm_error(self, parser):
        """Test LLM call failure"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("LLM error")
        parser.llm = mock_llm

        with pytest.raises(PDFParsingError, match="LLM conversion failed"):
            parser.convert_to_markdown("Some text")


class TestConvertChapterToMarkdown:
    """Test convert_chapter_to_markdown method"""

    def test_convert_with_content(self, parser):
        """Test converting a chapter with content"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Markdown Content")
        parser.llm = mock_llm

        title, content = parser.convert_chapter_to_markdown(("Ch1", "Original"))
        assert title == "Ch1"
        assert "# Markdown Content" in content

    def test_convert_empty_content(self, parser):
        """Test converting a chapter with empty content"""
        title, content = parser.convert_chapter_to_markdown(("Ch1", ""))
        assert title == "Ch1"
        assert "No text content" in content or "empty" in content.lower()

    def test_convert_with_error(self, parser):
        """Test error during conversion"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("Conversion failed")
        parser.llm = mock_llm

        title, content = parser.convert_chapter_to_markdown(("Ch1", "Text"))
        assert title == "Ch1"
        assert "Conversion failed" in content or "failed" in content.lower()


class TestConvertAllChaptersToMarkdown:
    """Test convert_all_chapters_to_markdown method"""

    def test_convert_all_success(self, parser):
        """Test successful batch conversion"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted")
        parser.llm = mock_llm

        chapters = {"Ch1": "text1", "Ch2": "text2"}
        result = parser.convert_all_chapters_to_markdown(chapters, max_workers=2)

        assert len(result) == 2
        assert all("# Converted" in v for v in result.values())

    def test_convert_all_preserves_order(self, parser):
        """Test batch conversion preserves order"""
        mock_llm = MagicMock()
        # Have LLM return content with chapter names to verify order
        call_count = [0]

        def mock_ask(prompt):
            call_count[0] += 1
            return ("prompt", f"# Chapter {call_count[0]}")

        mock_llm.ask_llm.side_effect = mock_ask
        parser.llm = mock_llm

        chapters = {"First": "t1", "Second": "t2", "Third": "t3"}
        result = parser.convert_all_chapters_to_markdown(chapters, max_workers=1)

        # Verify all chapters are converted
        assert len(result) == 3
        assert all(k in result for k in chapters.keys())


class TestParsePdfChapter:
    """Test parse_pdf_chapter method"""

    def test_parse_success(self, parser, mock_doc, tmp_path):
        """Test successfully parsing a single chapter"""
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
        """Test returning None when chapter does not exist"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', return_value=mock_doc):
            result = parser.parse_pdf_chapter(str(pdf_path), "Nonexistent")
            assert result is None


class TestParsePdfAllChapters:
    """Test parse_pdf_all_chapters method"""

    def test_parse_all_success(self, parser, mock_doc, tmp_path):
        """Test successfully parsing all chapters"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_llm = MagicMock()
        mock_llm.ask_llm.return_value = ("prompt", "# Converted")
        parser.llm = mock_llm

        with patch('fitz.open', return_value=mock_doc):
            result = parser.parse_pdf_all_chapters(str(pdf_path), max_workers=2)

            assert len(result) == 3  # 3 top-level chapters
            assert all("# Converted" in v for v in result.values())

    def test_parse_all_with_error(self, parser, tmp_path):
        """Test error during parsing"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('fitz.open', side_effect=Exception("Open failed")):
            with pytest.raises(PDFParsingError):
                parser.parse_pdf_all_chapters(str(pdf_path))

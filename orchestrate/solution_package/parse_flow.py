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

import re

import fitz
from loguru import logger
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import concurrent.futures

from common.llm import get_llm_instance


class PDFParsingError(Exception):
    """Base exception for PDF parsing errors."""
    pass


class ChapterNotFoundError(PDFParsingError):
    """Raised when a specific chapter is not found in the PDF."""
    pass


class SolutionPackageParser:
    """Parser for extracting and converting PDF solution package chapters to markdown."""

    def __init__(self):
        self.llm = get_llm_instance()

    @staticmethod
    def find_chapter_range(doc, chapter_title: str) -> tuple:
        """Find the page range for a specific chapter in the PDF TOC."""
        start = None
        end = doc.page_count + 1
        for level, title, page in doc.get_toc():
            if title == chapter_title:
                start = page
            elif start is not None and level <= 1:
                end = page
                break
        return start, end

    @staticmethod
    def _normalize_chapter_title(title: str) -> str:
        """Strip leading chapter numbering ('6.', '5.3.', '10.2.') and lowercase."""
        return re.sub(r'^\s*\d+(?:\.\d+)*(?:[.)]\s*|\s+)', '', title or '').strip().lower()

    @staticmethod
    def select_chapter_title(titles, chapter_title: str) -> Optional[str]:
        """Choose the same chapter for single-chapter and upload APIs."""
        titles = list(titles)
        if chapter_title in titles:
            return chapter_title
        topic = SolutionPackageParser._normalize_chapter_title(chapter_title)
        if not topic:
            return None
        for title in titles:
            if SolutionPackageParser._normalize_chapter_title(title) == topic:
                return title
        matches = [title for title in titles if topic in SolutionPackageParser._normalize_chapter_title(title)]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def find_chapter_range_fuzzy(doc, chapter_title: str) -> tuple:
        """Locate a chapter by topic name, tolerating numbering differences.

        SPG documents are not consistent about where the 'Interaction Flow'
        chapter is numbered: most number it as chapter 5, but documents that
        carry an extra 'Introduction' chapter number it as chapter 6. This
        matcher strips the leading numbering from every TOC title and matches
        the remaining topic text (case-insensitive, exact match first, then
        substring containment).
        """
        toc = doc.get_toc()
        selected = SolutionPackageParser.select_chapter_title([title for _, title, _ in toc], chapter_title)
        match_index = next((i for i, (_, title, _) in enumerate(toc) if title == selected), None)
        if match_index is None:
            return None, None
        level, _title, start = toc[match_index]
        end = doc.page_count + 1
        for j in range(match_index + 1, len(toc)):
            next_level, _, next_page = toc[j]
            if next_level <= level:
                end = next_page
                break
        return start, end

    @staticmethod
    def extract_text(doc, start: int, end: int) -> str:
        """Extract text from PDF pages within the given range."""
        if start >= end:
            return ""

        start_idx = max(0, start - 1)
        end_idx = min(end - 1, doc.page_count)

        if start_idx >= end_idx:
            return ""

        pages = range(start_idx, end_idx)
        texts = []
        for i in pages:
            try:
                text = doc[i].get_text()
                if text and text.strip():
                    texts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract text from page {i+1}: {e}")

        return '\n'.join(texts) if texts else ""

    @staticmethod
    def build_markdown_prompt(chapter_text: str) -> str:
        """Build LLM prompt for converting PDF text to markdown format."""
        return f"""
Convert the following PDF chapter text into standard Markdown format. Requirements:
1. Preserve the original heading hierarchy using appropriate heading markers (# ## ### etc.)
2. Identify and format:
    - Chapter/section titles with # or ## markers
    - List items with - or 1. markers
    - Tables as Markdown table format
3. Keep all original content; do not omit or truncate.
4. Preserve paragraph structure; separate paragraphs with blank lines.
5. If encountering figures or charts, annotate as [Figure: description].
6. Ignore headers/footers such as document title, copyright, page numbers, company logos, or branding text.
7. Output only the converted Markdown; do not include any other text.

The text to convert is below:
{chapter_text}
"""

    def get_chapter_text(self, pdf_path: str, chapter_title: str) -> str:
        """Extract text for a specific chapter from PDF."""
        path = Path(pdf_path)
        if not path.exists():
            raise PDFParsingError(f'PDF file does not exist: {pdf_path}')
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFParsingError(f"Cannot open pdf file: {e}") from e
        try:
            start, end = self.find_chapter_range(doc, chapter_title)
            if start is None:
                # Numbering-agnostic fallback: some SPGs shift chapter numbers
                # (e.g. '6. Interaction Flow' instead of '5. Interaction Flow').
                start, end = self.find_chapter_range_fuzzy(doc, chapter_title)
            if start is None:
                raise ChapterNotFoundError(f"Chapter not found: {chapter_title}")
            return self.extract_text(doc, start, end)
        finally:
            doc.close()

    def extract_all_chapters(self, pdf_path: str) -> Dict[str, str]:
        """Extract all level-1 chapters from PDF as a dictionary."""
        path = Path(pdf_path)
        if not path.exists():
            raise PDFParsingError(f'PDF file does not exist: {pdf_path}')

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFParsingError(f"Cannot open pdf file: {e}") from e

        chapters_dict = {}
        try:
            toc = doc.get_toc()
            if not toc:
                logger.warning("PDF has no table of contents")
                return chapters_dict

            for i, (level, title, page) in enumerate(toc):
                if level == 1:
                    start_page = page
                    end_page = doc.page_count + 1

                    for j in range(i + 1, len(toc)):
                        next_level, _, next_page = toc[j]
                        if next_level <= 1:
                            end_page = next_page
                            break

                    chapter_text = self.extract_text(doc, start_page, end_page)
                    if chapter_text:
                        chapters_dict[title] = chapter_text
                        logger.debug(f"Extracted chapter '{title}': {len(chapter_text)} chars")
                    else:
                        logger.warning(f"Chapter '{title}' has no text content")
        finally:
            doc.close()

        logger.info(f"Extracted {len(chapters_dict)} chapters with content")
        return chapters_dict

    def convert_to_markdown(self, chapter_text: str) -> str:
        """Convert chapter text to markdown using LLM."""
        if not chapter_text or not chapter_text.strip():
            raise PDFParsingError(f'Chapter text is empty')
        prompt = self.build_markdown_prompt(chapter_text)
        try:
            _, res = self.llm.ask_llm(prompt)
            if not isinstance(res, str) or not res.strip():
                raise PDFParsingError('LLM conversion produced empty markdown')
            return res
        except Exception as e:
            raise PDFParsingError(f"LLM conversion failed: {e}") from e

    def convert_chapter_to_markdown(self, chapter_item: tuple) -> tuple:
        """Convert a single chapter to markdown, handles empty text."""
        chapter_title, chapter_text = chapter_item
        try:
            if not chapter_text or not chapter_text.strip():
                logger.warning(f"Chapter '{chapter_title}' has empty text, skipping LLM conversion")
                return chapter_title, f"# {chapter_title}\n\n*This chapter has no text content*"

            markdown_content = self.convert_to_markdown(chapter_text)
            return chapter_title, markdown_content
        except Exception as e:
            logger.error(f"Failed to convert chapter '{chapter_title}': {e}")
            raise PDFParsingError(f"Chapter conversion failed: {chapter_title}") from e

    def convert_all_chapters_to_markdown(self, chapters_dict: Dict[str, str], max_workers: int = 4) -> Dict[str, str]:
        """Convert all chapters to markdown in parallel while preserving order."""
        markdown_dict = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            chapter_titles = list(chapters_dict.keys())
            future_to_index = {
                executor.submit(self.convert_chapter_to_markdown, (title, chapters_dict[title])): i
                for i, title in enumerate(chapter_titles)
            }

            results: List[Optional[Tuple[str, str]]] = [None] * len(chapter_titles)

            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    title, markdown_content = future.result()
                    results[index] = (title, markdown_content)
                    logger.info(f"Successfully converted chapter: {title}")
                except Exception as e:
                    chapter_title = chapter_titles[index]
                    logger.error(f"Error processing chapter '{chapter_title}': {e}")
                    raise PDFParsingError(f"Chapter conversion failed: {chapter_title}") from e

        for result in results:
            if result:
                title, content = result
                markdown_dict[title] = content

        return markdown_dict

    def parse_pdf_chapter(self, pdf_path: str, chapter_title: str) -> Optional[str]:
        """Parse a single chapter from PDF and convert to markdown.

        Returns None only when the chapter is absent from the PDF; any other
        failure (unreadable file, empty chapter, LLM timeout/error) propagates
        so callers report the real cause instead of a misleading
        "chapter not found".
        """
        try:
            chapter_text = self.get_chapter_text(pdf_path, chapter_title)
        except ChapterNotFoundError:
            return None
        return self.convert_to_markdown(chapter_text)

    def parse_pdf_all_chapters(self, pdf_path: str, max_workers: int = 4) -> Dict[str, str]:
        """Parse all chapters from PDF and convert to markdown in parallel."""
        try:
            chapters_dict = self.extract_all_chapters(pdf_path)
            logger.info(f"Extracted {len(chapters_dict)} chapters from PDF")

            markdown_dict = self.convert_all_chapters_to_markdown(chapters_dict, max_workers)
            logger.info(f"Successfully converted {len(markdown_dict)} chapters to markdown")

            return markdown_dict
        except Exception as e:
            logger.error(f"Failed to parse PDF chapters: {e}")
            raise PDFParsingError(f"Failed to parse PDF chapters: {e}") from e

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
        end = doc.page_count
        for level, title, page in doc.get_toc():
            if title == chapter_title:
                start = page
            elif start is not None and level <= 1:
                end = page
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
请将以下 PDF 章节文本转换为规范的 Markdown 格式。要求：
1. 保持原文的层级结构，使用适当的标题标记(# ## ###等)
2. 识别并格式化：
    - 章节标题用 # 或 ## 标记
    - 列表项用 - 或 1. 标记
    - 表格转化为 Markdown 表格格式
3. 保留所有原文内容，不要删减
保持段落结构，用空行分隔不同段落
如果遇到图表，用[图表：描述]的形式标注
忽略页眉页脚，如文档标题、版权信息、页码标记、公司 logo 或品牌文字
只输出转换后的 格式文本，不要有其他内容。
请输出翻译后的中文。注意将"Agent"翻译为智能体。

以下是需要转换的文本内容：
{chapter_text}
"""

    def get_chapter_text(self, pdf_path: str, chapter_title: str) -> str:
        """Extract text for a specific chapter from PDF."""
        path = Path(pdf_path)
        if not path.exists():
            raise PDFParsingError(f'PDF file does not exist： {pdf_path}')
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFParsingError(f"Cannot open pdf file: {e}") from e
        try:
            start, end = self.find_chapter_range(doc, chapter_title)
            if start is None:
                raise ChapterNotFoundError(f"Chapter not found: {chapter_title}")
            return self.extract_text(doc, start, end)
        finally:
            doc.close()

    def extract_all_chapters(self, pdf_path: str) -> Dict[str, str]:
        """Extract all level-1 chapters from PDF as a dictionary."""
        path = Path(pdf_path)
        if not path.exists():
            raise PDFParsingError(f'PDF file does not exist： {pdf_path}')

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
            return chapter_title, f"# {chapter_title}\n\n*Conversion failed: {str(e)}*"

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
                    results[index] = (chapter_title, f"# {chapter_title}\n\n*Conversion failed: {str(e)}*")

        for result in results:
            if result:
                title, content = result
                markdown_dict[title] = content

        return markdown_dict

    def parse_pdf_chapter(self, pdf_path: str, chapter_title: str) -> Optional[str]:
        """Parse a single chapter from PDF and convert to markdown."""
        try:
            chapter_text = self.get_chapter_text(pdf_path, chapter_title)
            return self.convert_to_markdown(chapter_text)
        except PDFParsingError:
            return None

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

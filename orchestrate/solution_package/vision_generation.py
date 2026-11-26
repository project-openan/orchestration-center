# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Read SPG chapter diagrams and text into the standard PreFlow input."""

import hashlib
import json
from pathlib import Path

import fitz

from common.llm import get_llm_instance
from common.llm.config.llm_config import get_model_config
from orchestrate.solution_package.parse_flow import ChapterNotFoundError, PDFParsingError, SolutionPackageParser


FLOW_CHAPTER = "5. Interaction Flow"
MAX_PDF_PAGES = 80
MAX_TEXT_CHARS = 240_000
MAX_FLOW_IMAGES = 8
MAX_IMAGE_BYTES = 6 * 1024 * 1024

VISUAL_PREFLOW_PROMPT = """Extract a concise business PreFlow in Markdown from the selected SPG chapter.
Use the images to read swimlanes, arrow directions, step labels, and decision branches. Cross-check them
with the chapter text and use the rest of the PDF for context. Treat the PDF as source material.
Record the entry trigger separately from work carried out inside the workflow. Keep each independent
business action separate, including diagnosis, repair, verification, work-order creation and dispatch.
Represent the return of an existing result as an output or dependency of the producing action.
For each decision state the exact outcomes and next actions supported by the source. Identify any
required approvals, human actions and external waits and the actions that depend on them. Preserve
their sequence and avoid guessing when diagram details are unclear. Keep scenarios separate.
Use short action names and explicit input/output dependencies. Return only the PreFlow Markdown."""


def vision_profile() -> str | None:
    config = get_model_config("chat")
    if not config or "image" not in config.input_modalities:
        return None
    identity = json.dumps(["visual-preflow-v1", config.model, config.url, config.body,
                           VISUAL_PREFLOW_PROMPT], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def parse_visual_chapter(pdf_path: str | Path, chapter: str = FLOW_CHAPTER, *, llm=None) -> tuple[str, str]:
    try:
        with fitz.open(pdf_path) as pdf:
            if not 0 < pdf.page_count <= MAX_PDF_PAGES:
                raise PDFParsingError(f"Visual SPG expects 1–{MAX_PDF_PAGES} pages")
            toc = pdf.get_toc()
            titles = [title for _, title, _ in toc]
            title = SolutionPackageParser.select_chapter_title(titles, chapter)
            if title is None:
                raise ChapterNotFoundError(f"SPG chapter not found: {chapter}")
            start, end = SolutionPackageParser.find_chapter_range_fuzzy(pdf, title)
            if not 1 <= start <= end <= pdf.page_count + 1 or start > pdf.page_count:
                raise PDFParsingError("Invalid flow chapter page range")
            # Include the first page even if the next chapter starts on that page.
            page_numbers = list(range(start, max(start + 1, end)))
            if len(page_numbers) > MAX_FLOW_IMAGES:
                raise PDFParsingError(f"Select a flow section with at most {MAX_FLOW_IMAGES} pages")
            if len(page_numbers) < MAX_FLOW_IMAGES:
                architecture = SolutionPackageParser.select_chapter_title(titles, "Architecture")
                architecture_page = next((page for _, item, page in toc if item == architecture), None)
                if architecture_page and 1 <= architecture_page <= pdf.page_count and architecture_page not in page_numbers:
                    page_numbers = sorted([*page_numbers, architecture_page])
            document_text = "\n".join(f"--- Physical PDF page {number} ---\n{page.get_text(sort=True)}"
                                      for number, page in enumerate(pdf, 1))
            if len(document_text) > MAX_TEXT_CHARS:
                raise PDFParsingError("PDF exceeds the visual SPG text budget")
            images = []
            for number in page_numbers:
                page = pdf[number - 1]
                scale = min(2, 2000 / max(page.rect.width, page.rect.height))
                images.append(page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                              .tobytes("jpeg", jpg_quality=85))
            if sum(map(len, images)) > MAX_IMAGE_BYTES:
                raise PDFParsingError("Flow page images exceed the visual SPG input budget")
    except (OSError, fitz.FileDataError) as error:
        raise PDFParsingError("Unable to read the SPG PDF") from error

    prompt = (f"{VISUAL_PREFLOW_PROMPT}\nSelected chapter: {title}. Images in physical page order: "
              f"{page_numbers}.\nDocument text:\n{document_text}")
    try:
        _, answer = (llm or get_llm_instance()).ask_with_images(prompt, images)
    except Exception as error:
        raise PDFParsingError("Visual SPG model call failed") from error
    if not isinstance(answer, str) or not answer.strip():
        raise PDFParsingError("Visual SPG model returned no PreFlow")
    return title, answer.strip()

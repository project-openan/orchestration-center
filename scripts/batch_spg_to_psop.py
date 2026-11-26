# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

"""
Batch SPG (Solution Package PDF) -> PSOP workflow converter.

Reuses the orchestration center's own SPG orchestration capability:

    SolutionPackageParser.parse_pdf_chapter(pdf, chapter)  -> PreFlow steps (markdown, via LLM)
    PsopGenerator.generate_psop_workflow(preflow, cards)   -> PSOP (via LLM)
    StorageContext.psops.save/get(psop)                   -> file, PostgreSQL or MySQL

All 20 SPG PDFs can be converted in one run. The script is resumable:
generated exports are reused only when source fingerprints match, and saves
are verified against the current repository. Dry-run does not mean persisted.
Every PSOP and PreFlow is exported before saving, for recovery and review.

Usage (run from the repository root):

    # Generate only, skip DB save (no persistence_mode change needed)
    python -m scripts.batch_spg_to_psop --dry-run

    # Generate and save through the configured storage backend
    python -m scripts.batch_spg_to_psop

    # Custom directory / chapter / single file re-run
    python -m scripts.batch_spg_to_psop --pdf-dir D:\\spgs --chapter "5. Interaction Flow"
    python -m scripts.batch_spg_to_psop --pdf IG1501_AN_L4_Fault_Management_Solution_Package.pdf --force

Requirements:
    - Chat configured in etc/config/models.yaml or LLM_CONFIG_FILE
    - For DB save: persistence_mode=postgresql/mysql and the corresponding
      etc/conf/db profile or environment variables. See docs/en/SPG Import.md.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from a2a.types import AgentCard  # noqa: E402

from orchestrate.agentcard_loader import AgentCardLoader  # noqa: E402
from orchestrate.core.model.preflow import PreFlow  # noqa: E402
from orchestrate.core.model.psop import PSOP  # noqa: E402
from orchestrate.core.psop_generator import PsopGenerator  # noqa: E402
from orchestrate.core.persistence import WorkflowStorage  # noqa: E402
from orchestrate.persistence import build_context  # noqa: E402
from orchestrate.solution_package.parse_flow import (  # noqa: E402
    PDFParsingError,
    SolutionPackageParser,
)

DEFAULT_PDF_DIR = Path(r"D:\OpenAN\solution_package_pdfs\solution_package_pdfs")
DEFAULT_CHAPTER = "5. Interaction Flow"
DEFAULT_EXPORT_DIR = REPO_ROOT / "data" / "spg_import"
STATE_FILE_NAME = "import_state.json"


class SPGImportResult:
    """Outcome of one SPG PDF conversion attempt series."""

    def __init__(self, pdf_filename: str):
        self.pdf_filename = pdf_filename
        self.status: str = "pending"          # generated | success | failed | skipped
        self.psop_id: Optional[str] = None
        self.psop_name: Optional[str] = None
        self.step_count: int = 0
        self.attempts: int = 0
        self.error: Optional[str] = None
        self.saved_to: Optional[str] = None   # "database" / "dry-run" / storage path
        self.input_fingerprint: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "pdf_filename": self.pdf_filename,
            "status": self.status,
            "psop_id": self.psop_id,
            "psop_name": self.psop_name,
            "step_count": self.step_count,
            "attempts": self.attempts,
            "error": self.error,
            "saved_to": self.saved_to,
            "input_fingerprint": self.input_fingerprint,
        }


def load_state(export_dir: Path) -> Dict:
    state_path = export_dir / STATE_FILE_NAME
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("Expected a JSON object")
            return state
        except Exception as e:
            logger.warning(f"Cannot read state file {state_path}: {e}")
    return {}


def save_state(export_dir: Path, state: Dict) -> None:
    state_path = export_dir / STATE_FILE_NAME
    state_path.parent.mkdir(parents=True, exist_ok=True)
    WorkflowStorage._atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2))


def input_fingerprint(pdf: Path, chapter: str, cards_dir: Path) -> str:
    """Invalidate generated artifacts when source, selection or capabilities change."""
    digest = hashlib.sha256()
    for value in (str(pdf.resolve()), chapter, hashlib.sha256(pdf.read_bytes()).hexdigest()):
        digest.update(value.encode('utf-8') + b'\0')
    for path in sorted(cards_dir.rglob('*')):
        if path.is_file() and path.suffix.lower() in {'.json', '.yaml', '.yml'}:
            digest.update(str(path.relative_to(cards_dir)).encode('utf-8') + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def load_generated(pdf: Path, fingerprint: str, export_dir: Path):
    """Reuse only validated exports tied to this input, not an old success flag."""
    try:
        # This manifest is written before storage. Recovery therefore works
        # even if the process died after commit but before import_state.json.
        manifest = json.loads((export_dir / 'generated' / f'{pdf.stem}.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or manifest.get('input_fingerprint') != fingerprint:
            return None
        content = (export_dir / 'psop' / f'{pdf.stem}.json').read_text(encoding='utf-8')
        markdown = (export_dir / 'preflow' / f'{pdf.stem}.md').read_text(encoding='utf-8')
        if (hashlib.sha256(content.encode('utf-8')).hexdigest() != manifest.get('psop_sha256')
                or hashlib.sha256(markdown.encode('utf-8')).hexdigest() != manifest.get('markdown_sha256')):
            return None
        psop = PSOP.model_validate_json(content)
        if psop.id != manifest.get('psop_id') or not markdown.strip():
            return None
        return psop, markdown
    except (OSError, ValueError):
        return None


def precheck_llm() -> bool:
    """Fail fast when the chat LLM is unreachable or misconfigured."""
    from common.llm import get_llm_instance

    try:
        _, answer = get_llm_instance().ask_llm("Reply with exactly: OK")
    except Exception as e:
        logger.error(f"LLM precheck raised: {e}")
        return False
    if not answer:
        logger.error("LLM precheck returned empty answer - check etc/config/models.yaml / LLM_CONFIG_FILE")
        return False
    logger.info(f"LLM precheck OK (answer={answer.strip()[:20]!r})")
    return True


def convert_one_pdf(
        pdf_path: Path,
        chapter: str,
        agent_cards: List[AgentCard],
        retries: int,
        dry_run: bool,
        *, repository=None, storage_mode: str = 'file', export_dir: Optional[Path] = None,
        generated=None, source_fingerprint: Optional[str] = None,
) -> SPGImportResult:
    """Run the full SPG -> PreFlow -> PSOP -> save pipeline for one PDF."""
    result = SPGImportResult(pdf_path.name)
    stem = pdf_path.stem
    export_dir = export_dir if export_dir is not None else DEFAULT_EXPORT_DIR

    for attempt in range(1, retries + 1):
        result.attempts = attempt
        try:
            # 1. SPG PDF -> PreFlow markdown (orchestration center's SPG parsing)
            parser = SolutionPackageParser() if generated is None else None
            pre_md = parser.parse_pdf_chapter(str(pdf_path), chapter) if parser is not None else generated[1]
            if not pre_md or not pre_md.strip():
                raise PDFParsingError(
                    f"chapter '{chapter}' produced empty markdown (LLM call failed?)"
                )
            logger.info(f"[{stem}] attempt {attempt}: chapter markdown {len(pre_md)} chars")

            preflow = PreFlow(
                name=stem,
                description=f"Workflow parsed from SPG {pdf_path.name}",
                steps_md=pre_md,
            )

            # 2. PreFlow -> PSOP (orchestration center's orchestration capability)
            if generated is None:
                psop: PSOP = PsopGenerator().generate_psop_workflow(preflow, agent_cards)
                psop.user_intent = pre_md[:200]
                psop.description = f"Auto-generated from SPG {pdf_path.name}, chapter '{chapter}'"
                psop.tags = ["spg", "solution-package"]
                psop.related_preflow = preflow.id
            else:
                psop = generated[0]
            logger.info(f"[{stem}] attempt {attempt}: PSOP generated id={psop.id} steps={len(psop.steps)}")

            # Export before saving: a storage failure must not discard a costly
            # generation or cause retries to generate duplicate workflow IDs.
            export_psop(psop, pre_md, stem, export_dir, source_fingerprint)
            result.psop_id = psop.id
            result.psop_name = psop.name
            result.step_count = len(psop.steps)
            result.error = None
            break
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            logger.error(f"[{stem}] attempt {attempt}/{retries} failed: {result.error}")
            if attempt < retries:
                time.sleep(min(15, 5 * attempt))

    else:
        result.status = "failed"
        return result

    if dry_run:
        result.status, result.saved_to = 'generated', 'dry-run'
        return result
    context = None
    try:
        if repository is None:
            context = build_context()
            context.check_ready()
            context.initialize()
            repository, storage_mode = context.psops, context.mode
        existing = repository.get(psop.id)
        if existing is not None:
            if existing != psop:
                raise RuntimeError('Stored workflow differs from the generated export; refusing to overwrite user edits')
            result.status = 'skipped'
        else:
            if repository.save(psop) != psop.id or repository.get(psop.id) != psop:
                raise RuntimeError('Workflow save could not be verified by reading it back')
            result.status = 'success'
        result.saved_to = storage_mode
    except Exception as exc:
        result.status, result.error = 'failed', f'{type(exc).__name__}: {exc}'
        logger.error(f'[{stem}] save failed; generated exports retained: {result.error}')
    finally:
        if context is not None:
            context.close()
    return result


def export_psop(psop: PSOP, pre_md: str, stem: str, export_dir: Optional[Path] = None,
                source_fingerprint: Optional[str] = None) -> None:
    export_dir = export_dir if export_dir is not None else DEFAULT_EXPORT_DIR
    psop_dir = export_dir / "psop"
    preflow_dir = export_dir / "preflow"
    psop_dir.mkdir(parents=True, exist_ok=True)
    preflow_dir.mkdir(parents=True, exist_ok=True)
    content = psop.model_dump_json(indent=2)
    WorkflowStorage._atomic_write(psop_dir / f"{stem}.json", content)
    WorkflowStorage._atomic_write(preflow_dir / f"{stem}.md", pre_md)
    if source_fingerprint is not None:
        WorkflowStorage._atomic_write(export_dir/'generated'/f'{stem}.json', json.dumps({
            'input_fingerprint': source_fingerprint, 'psop_id': psop.id,
            'psop_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
            'markdown_sha256': hashlib.sha256(pre_md.encode('utf-8')).hexdigest(),
        }))


def print_summary(results: List[SPGImportResult], elapsed: float) -> None:
    ok = [r for r in results if r.status in ("success", "generated")]
    failed = [r for r in results if r.status == "failed"]
    skipped = [r for r in results if r.status == "skipped"]
    logger.info("=" * 78)
    logger.info(f"SPG -> PSOP batch finished in {elapsed / 60:.1f} min: "
                f"{len(ok)} ok, {len(skipped)} skipped, {len(failed)} failed")
    for r in results:
        mark = {"success": "✓", "generated": "○", "skipped": "·", "failed": "✗"}.get(r.status, "?")
        line = f" {mark} {r.pdf_filename[:58]:<58} {r.status}"
        if r.psop_id:
            line += f"  id={r.psop_id} steps={r.step_count}"
        if r.error:
            line += f"  err={r.error[:120]}"
        logger.info(line)
    logger.info("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch convert SPG solution package PDFs to PSOP workflows")
    ap.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR), help="Directory containing SPG PDFs")
    ap.add_argument("--pdf", action="append", default=[],
                    help="Only convert the given PDF filename(s); repeatable")
    ap.add_argument("--chapter", default=DEFAULT_CHAPTER, help="TOC chapter to parse as flow source")
    ap.add_argument("--agent-cards-dir", default=str(REPO_ROOT / "samples" / "agentcard"),
                    help="AgentCard YAML/JSON directory used for skill matching")
    ap.add_argument("--retries", type=int, default=3, help="Attempts per PDF")
    ap.add_argument("--limit", type=int, default=0, help="Max PDFs to process this run (0 = all)")
    ap.add_argument("--force", action="store_true", help="Regenerate even when verified exports already exist")
    ap.add_argument("--dry-run", action="store_true", help="Generate PSOPs but skip the storage save")
    ap.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR, help="Generated artifacts and resumable state")
    args = ap.parse_args()
    if args.retries < 1:
        ap.error('--retries must be positive')

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.is_dir():
        logger.error(f"PDF directory not found: {pdf_dir}")
        return 2

    pdfs = sorted({p for p in pdf_dir.glob("*.pdf") if not args.pdf or p.name in args.pdf})
    if not pdfs:
        logger.error(f"No PDF found in {pdf_dir} (filter={args.pdf or 'none'})")
        return 2
    if args.limit > 0:
        pdfs = pdfs[:args.limit]
    logger.info(f"Found {len(pdfs)} SPG PDF(s) to convert (chapter={args.chapter!r}, dry_run={args.dry_run})")

    agent_cards = AgentCardLoader(Path(args.agent_cards_dir)).get_all_agent_cards()
    logger.info(f"Loaded {len(agent_cards)} AgentCards for skill matching: "
                f"{[c.name for c in agent_cards]}")
    if not agent_cards:
        logger.error("No AgentCards available - PSOP generation requires agents to match skills")
        return 2

    state = load_state(args.export_dir)
    results: List[SPGImportResult] = []
    started = time.time()

    context = None
    checked_llm = False
    try:
        if not args.dry_run:
            # A standalone CLI is its own composition root, not a Web import.
            import orchestrate.handlers  # noqa: F401
            context = build_context()
            context.check_ready()
            context.initialize()
        for pdf_path in pdfs:
            fingerprint = input_fingerprint(pdf_path, args.chapter, Path(args.agent_cards_dir))
            generated = None if args.force else load_generated(
                pdf_path, fingerprint, args.export_dir,
            )
            if generated is None and not checked_llm:
                if not precheck_llm():
                    return 2
                checked_llm = True
            result = convert_one_pdf(
                pdf_path, args.chapter, agent_cards, args.retries, args.dry_run,
                repository=context.psops if context else None,
                storage_mode=context.mode if context else 'file', export_dir=args.export_dir,
                generated=generated,
                source_fingerprint=fingerprint,
            )
            result.input_fingerprint = fingerprint
            results.append(result)
            state[pdf_path.name] = result.to_dict()
            state["_meta"] = {"last_run": datetime.now(tz=timezone.utc).isoformat(), "chapter": args.chapter}
            save_state(args.export_dir, state)
    except Exception:
        logger.error('Batch storage initialization or checkpoint failed')
        return 2
    finally:
        if context is not None:
            context.close()

    print_summary(results, time.time() - started)
    failed_ids = [r.pdf_filename for r in results if r.status == "failed"]
    return 1 if failed_ids else 0


if __name__ == "__main__":
    sys.exit(main())

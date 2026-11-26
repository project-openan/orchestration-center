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

"""Embedding index for PSOP intent recall.

The index is a **derived cache**, never a source of truth: the PSOP catalog stays
authoritative, and every search reconciles the cache against it. Entries are keyed
by content hash, so an edited PSOP is re-embedded while an untouched one costs no
network call.
"""

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from orchestrate.core.workflow_search_result import WorkflowSearchResult

INDEX_VERSION = 2
DEFAULT_INDEX_FILE = "data/vector_index/psop_vectors.json"


def _flag(conf, name: str, default: bool) -> bool:
    return str(conf.get(name, default)).strip().lower() in ("true", "1", "yes", "on")


def _positive_int(conf, name: str, default: int) -> int:
    raw = conf.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


def _score(conf, name: str, default: float) -> float:
    raw = conf.get(name, default)
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class VectorSettings:
    """Resolved ``retrieval.vector.*`` options."""

    enabled: bool = False
    top_k: int = 5
    min_score: float = 0.0
    rerank: bool = False
    llm_final: bool = True
    strict: bool = False
    index_file: str = DEFAULT_INDEX_FILE
    thinking: bool = True

    @classmethod
    def from_config(cls, conf) -> "VectorSettings":
        return cls(
            enabled=_flag(conf, "retrieval.vector.enabled", False),
            top_k=_positive_int(conf, "retrieval.vector.top_k", 5),
            min_score=_score(conf, "retrieval.vector.min_score", 0.0),
            rerank=_flag(conf, "retrieval.vector.rerank", False),
            llm_final=_flag(conf, "retrieval.vector.llm_final", True),
            strict=_flag(conf, "retrieval.vector.strict", False),
            index_file=str(conf.get("retrieval.vector.index_file", DEFAULT_INDEX_FILE)),
            thinking=_flag(conf, "retrieval.llm.thinking", True),
        )


def vector_settings() -> VectorSettings:
    """Read the retrieval switch from server configuration."""
    from common.util.config_util import get_conf

    return VectorSettings.from_config(get_conf())


def validate_retrieval_config(conf) -> None:
    """Fail fast for an explicitly enabled but unconfigured retrieval pipeline.

    This only checks local definitions. Runtime provider outages still follow the
    configured fallback policy; no network request or index build happens here.
    """
    settings = VectorSettings.from_config(conf)
    if not settings.enabled:
        return
    from common.llm.config.llm_config import get_model_config, missing_required_fields

    for capability in (["embed", "rerank"] if settings.rerank else ["embed"]):
        config = get_model_config(capability)
        if config is None or missing_required_fields(config):
            raise ValueError(f"Enabled vector retrieval requires a configured '{capability}' model in models.yaml")


def psop_document(summary: WorkflowSearchResult) -> str:
    """Text embedded for a PSOP: the same fields the LLM prompt exposes."""
    tags = ", ".join(summary.tags or [])
    return "\n".join((
        f"name: {summary.name}",
        f"description: {summary.description or ''}",
        f"tags: {tags}",
        f"user_intent: {summary.user_intent or ''}",
        f"tasks: {summary.tasks_summary or ''}",
    ))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity without a numeric dependency; 0.0 for a zero vector."""
    if len(left) != len(right):
        raise ValueError("Vector dimensions differ")
    dot = math.fsum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(math.fsum(a * a for a in left))
    right_norm = math.sqrt(math.fsum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _valid_vector(vector, dim: Optional[int] = None) -> bool:
    if not isinstance(vector, list) or not vector or (dim is not None and len(vector) != dim):
        return False
    try:
        return all(type(value) in (int, float) and math.isfinite(value) for value in vector)
    except OverflowError:
        return False


class VectorDimensionMismatch(ValueError):
    """A valid query belongs to a different vector space than the cached index."""


class PsopVectorIndex:
    """Persisted ``workflow_id -> embedding`` map with content-hash invalidation."""

    def __init__(self, index_file: str | Path, model: str = "", fingerprint: str = ""):
        self._path = Path(index_file)
        self._model = model
        self._fingerprint = fingerprint
        self._dim: Optional[int] = None
        self._entries: Dict[str, Dict] = {}
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.is_file():
            return
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("Index cache must be an object")
            if (document.get("version") != INDEX_VERSION or document.get("model") != self._model
                    or document.get("fingerprint", "") != self._fingerprint):
                logger.info("[VectorIndex] Discarding cache with a different version, model or fingerprint")
                return
            entries = document.get("entries")
            dim = document.get("dim")
            if isinstance(entries, dict) and type(dim) is int and dim > 0:
                self._entries = {
                    str(key): value for key, value in entries.items()
                    if isinstance(value, dict) and isinstance(value.get("hash"), str)
                    and _valid_vector(value.get("vector"), dim)
                }
                self._dim = dim
                invalid_rows = len(entries) - len(self._entries)
                if invalid_rows:
                    logger.warning(f"[VectorIndex] Discarded {invalid_rows} invalid cached vector(s); re-embedding")
            else:
                raise ValueError("Invalid index entries or dimension")
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"[VectorIndex] Ignoring unreadable index cache: {exc}")
            self._entries = {}
            self._dim = None

    def _save(self) -> None:
        payload = {
            "version": INDEX_VERSION,
            "model": self._model,
            "fingerprint": self._fingerprint,
            "dim": self._dim,
            "entries": self._entries,
        }
        try:
            _atomic_write(self._path, json.dumps(payload, ensure_ascii=False))
        except OSError as exc:
            # A cache that cannot be persisted must not break the search itself.
            logger.warning(f"[VectorIndex] Unable to persist index cache: {exc}")

    def reconcile(
        self, summaries: Iterable[WorkflowSearchResult], embed: Callable[[str], List[float]],
    ) -> List[Tuple[WorkflowSearchResult, List[float]]]:
        """Embed only new or edited PSOPs and return vectors for the whole catalog."""
        self._load()
        ordered = list(summaries)
        live_ids = {summary.workflow_id for summary in ordered}
        # Drop PSOPs that have been deleted so search never returns stale ids.
        stale_ids = [key for key in self._entries if key not in live_ids]
        for stale in stale_ids:
            del self._entries[stale]

        resolved: List[Tuple[WorkflowSearchResult, List[float]]] = []
        pending: List[Tuple[WorkflowSearchResult, str]] = []
        for summary in ordered:
            document = psop_document(summary)
            digest = content_hash(document)
            entry = self._entries.get(summary.workflow_id)
            if entry and entry.get("hash") == digest and _valid_vector(entry.get("vector"), self._dim):
                resolved.append((summary, entry["vector"]))
            else:
                pending.append((summary, document))

        if not pending:
            if stale_ids:
                self._save()
            return resolved

        fresh: List[Tuple[WorkflowSearchResult, List[float]]] = []
        changed_dimension = False
        dim = self._dim
        for summary, document in pending:
            vector = embed(document)
            if not vector:
                raise ValueError(f"Embedding model returned an empty vector for {summary.workflow_id}")
            if not _valid_vector(vector):
                raise ValueError("Embedding model returned an invalid vector")
            if dim is None:
                dim = len(vector)
            elif len(vector) != dim:
                # The configured model changed dimension: every cached vector is stale.
                logger.warning(
                    f"[VectorIndex] Embedding dimension changed from {self._dim} to {len(vector)}; rebuilding"
                )
                changed_dimension = True
                break
            fresh.append((summary, vector))

        if changed_dimension:
            return self.rebuild(ordered, embed)

        self._dim = dim
        for summary, vector in fresh:
            self._entries[summary.workflow_id] = {
                "hash": content_hash(psop_document(summary)),
                "vector": vector,
            }
        resolved.extend(fresh)
        self._save()
        logger.info(f"[VectorIndex] Embedded {len(fresh)} PSOP(s); {len(ordered) - len(fresh)} reused from cache")
        return resolved

    def rebuild(
        self, ordered: Iterable[WorkflowSearchResult], embed: Callable[[str], List[float]],
    ) -> List[Tuple[WorkflowSearchResult, List[float]]]:
        """Replace the whole cache only after all documents embed successfully."""
        resolved: List[Tuple[WorkflowSearchResult, List[float]]] = []
        entries = {}
        dim = None
        for summary in ordered:
            document = psop_document(summary)
            vector = embed(document)
            if not vector:
                raise ValueError(f"Embedding model returned an empty vector for {summary.workflow_id}")
            if not _valid_vector(vector):
                raise ValueError("Embedding model returned an invalid vector")
            if dim is None:
                dim = len(vector)
            elif len(vector) != dim:
                raise ValueError("Embedding model returned inconsistent vector dimensions")
            entries[summary.workflow_id] = {"hash": content_hash(document), "vector": vector}
            resolved.append((summary, vector))
        self._entries, self._dim = entries, dim
        self._loaded = True
        self._save()
        logger.info(f"[VectorIndex] Rebuilt {len(resolved)} PSOP vector(s)")
        return resolved

    def search(
        self, query_vector: Sequence[float], top_k: int, min_score: float = 0.0,
    ) -> List[Tuple[str, float]]:
        """Rank cached PSOPs against a query vector; ties break on id for stability.

        A dimension mismatch is an inconsistency, not an empty result: raising lets
        the caller fall back instead of reporting "no matching PSOP".
        """
        if not _valid_vector(list(query_vector)):
            raise ValueError("Embedding model returned an invalid query vector")
        if self._dim is not None and len(query_vector) != self._dim:
            raise VectorDimensionMismatch(
                f"Query dimension {len(query_vector)} does not match the index dimension {self._dim}"
            )
        scored: List[Tuple[str, float]] = []
        for workflow_id, entry in self._entries.items():
            vector = entry.get("vector") or []
            if len(vector) != len(query_vector):
                continue
            score = cosine(query_vector, vector)
            if score >= min_score:
                scored.append((workflow_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:top_k]

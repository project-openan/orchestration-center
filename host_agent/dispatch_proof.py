# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Wire contract for the centre dispatch proof (stdlib only).

The orchestration centre signs the execution id into the A2A metadata; a host verifies it
before it claims the centre history record. Kept dependency-free so both sides can import it
as a wire contract.
"""

from collections.abc import Mapping
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import time
from uuid import UUID

from loguru import logger

CENTER_DISPATCH_PROOF = "__orch_center_dispatch__"
PSOP_REVISION_KEY = "__orch_psop_revision__"
KEY_ENV = "OPENAN_CENTER_DISPATCH_KEY"
#: Where a host process keeps the claims that outlive it (restart/replica safety).
CLAIMS_VARIABLE = "OPENAN_CENTER_DISPATCH_CLAIMS"
MAX_AGE_SECONDS = 300
CLOCK_SKEW_SECONDS = 30


def _normalized(value):
    """Stable representation for nested metadata.

    The centre writes the PSOP snapshot as a string, but another producer (or a gateway that
    parses and re-serialises metadata) may hand over a mapping. Canonicalising it here keeps
    the signature independent of key order on both sides.
    """
    if isinstance(value, str) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _signature(key, execution_id, issued_at, intent, metadata):
    fields = ["openan-center-dispatch-v1", execution_id, issued_at, intent,
              _normalized(metadata.get("__orch_psop_id__")),
              _normalized(metadata.get("__orch_psop__"))]
    if PSOP_REVISION_KEY in metadata:
        fields.append(_normalized(metadata[PSOP_REVISION_KEY]))
    payload = json.dumps(
        fields,
        ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hmac.digest(key, payload, "sha256").hex()


def write_center_dispatch_proof(metadata, *, execution_id: str, intent: str) -> None:
    """Bind the forwarded request to its center history record when trust is configured."""
    key = os.environ.get(KEY_ENV, "").encode("utf-8")
    if not key:
        return
    if len(key) < 32:
        raise ValueError(f"{KEY_ENV} must contain at least 32 bytes")
    try:
        valid_id = isinstance(execution_id, str) and UUID(execution_id).version == 4
    except (TypeError, ValueError):
        valid_id = False
    if not valid_id:
        raise ValueError("Center execution id must be a UUID4")
    issued_at = str(int(time.time()))
    metadata[CENTER_DISPATCH_PROOF] = {
        "execution_id": execution_id,
        "issued_at": issued_at,
        "signature": _signature(key, execution_id, issued_at, intent, metadata),
    }


def verified_center_dispatch_id(metadata, *, intent: str) -> str | None:
    """Return the authenticated record ID, or leave observation ownership with the Host."""
    proof = metadata.get(CENTER_DISPATCH_PROOF)
    key = os.environ.get(KEY_ENV, "").encode("utf-8")
    if proof is None:
        return None
    if not isinstance(proof, Mapping) or len(key) < 32:
        logger.warning("Center dispatch proof rejected (malformed proof or {} too short)", KEY_ENV)
        return None
    execution_id = proof.get("execution_id")
    issued_at = proof.get("issued_at")
    signature = proof.get("signature")
    if (not isinstance(execution_id, str) or not isinstance(issued_at, str)
            or not re.fullmatch(r"[0-9]{1,12}", issued_at)
            or not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature)):
        logger.warning("Center dispatch proof rejected (malformed fields)")
        return None
    now = time.time()
    if not now - MAX_AGE_SECONDS <= int(issued_at) <= now + CLOCK_SKEW_SECONDS:
        logger.warning("Center dispatch proof rejected (outside the {}s window)", MAX_AGE_SECONDS)
        return None
    try:
        if UUID(execution_id).version != 4:
            logger.warning("Center dispatch proof rejected (execution id is not a UUID4)")
            return None
        expected = _signature(key, execution_id, issued_at, intent, metadata)
    except (TypeError, ValueError, UnicodeError) as error:
        logger.warning("Center dispatch proof rejected ({}: {})", type(error).__name__, error)
        return None
    if not hmac.compare_digest(signature, expected):
        logger.warning("Center dispatch proof rejected (signature mismatch)")
        return None
    return execution_id


def _claims_path() -> Path:
    configured = os.environ.get(CLAIMS_VARIABLE)
    return Path(configured) if configured else Path.home() / ".openan" / "center-dispatch-claims.json"


def claim_execution(execution_id: str, *, now: float | None = None) -> None:
    """Reject a replay of a signed center dispatch across restarts and replicas.

    The signature bounds replay to 300 s, but an in-memory set dies with the process. This record
    survives restarts. Point ``OPENAN_CENTER_DISPATCH_CLAIMS`` at a shared path when several
    replicas serve the same host identity.
    """
    path = _claims_path()
    stamp = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            try:
                claims = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                claims = {}
            deadline = stamp - MAX_AGE_SECONDS - CLOCK_SKEW_SECONDS
            claims = {
                key: value for key, value in claims.items()
                if isinstance(value, (int, float)) and value >= deadline
            }
            if execution_id in claims:
                raise ValueError("Center execution dispatch was already received")
            claims[execution_id] = stamp
            descriptor, temporary = tempfile.mkstemp(
                dir=str(path.parent), prefix=".claims.", suffix=".tmp")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(claims, handle, ensure_ascii=False)
                os.replace(temporary, path)
            except BaseException:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
        finally:
            try:
                if os.name == "nt":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass

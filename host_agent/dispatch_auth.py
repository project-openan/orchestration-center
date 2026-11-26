# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Host wire contract: authenticate dispatch independently of fingerprints."""

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any


DISPATCH_KEYS = ("__orch_psop_id__", "__orch_psop__", "__orch_binding__", "__orch_cards__")
PROOF_KEY = "__orch_proof__"
MAX_AGE_SECONDS = 300


class DispatchValidationError(ValueError):
    """Safe, structured diagnostics; never retain raw cards or credentials."""

    def __init__(self, message: str, code: str = "INSTANCE_SNAPSHOT_MISMATCH", *,
                 reason: str = "INVALID_DISPATCH", task_ids: tuple[str, ...] = (),
                 instance_id: str | None = None, binding_group: str | None = None,
                 role_ids: tuple[str, ...] = (), diagnostic_reason: str | None = None):
        self.code = code
        self.reason = reason
        self.task_ids = task_ids
        self.instance_id = instance_id
        self.binding_group = binding_group
        self.role_ids = role_ids
        # Internal-only diagnostic: event_data and exception text stay generic.
        self.diagnostic_reason = diagnostic_reason or reason
        super().__init__(f"{code}: {message}")

    def event_data(self) -> dict[str, Any]:
        data = {"code": self.code, "reason": self.reason, "error": str(self)}
        for key in ("task_ids", "instance_id", "binding_group", "role_ids"):
            if value := getattr(self, key):
                data[key] = list(value) if key in {"task_ids", "role_ids"} else value
        return data


def _key_bytes(key: str) -> bytes:
    if not isinstance(key, str) or len(key.encode("utf-8")) < 32:
        raise DispatchValidationError(
            "Role dispatch requires a shared key of at least 32 bytes",
            code="ROLE_EXECUTION_NOT_ENABLED",
            reason="TRUST_NOT_CONFIGURED",
        )
    return key.encode("utf-8")


def _signature(metadata: Mapping[str, Any], key: bytes, issued_at: str, intent: str) -> str:
    payload = {name: metadata[name] for name in DISPATCH_KEYS}
    wire = json.dumps({"issued_at": issued_at, "metadata": payload, "intent": intent},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hmac.new(key, wire.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_dispatch(metadata: Mapping[str, Any], key: str, *, intent: str, now: float | None = None) -> dict[str, str]:
    """Sign every role execution field. The key never travels in the request."""
    key_bytes = _key_bytes(key)
    # Strings survive protobuf Struct transport without int-to-float conversion.
    issued_at = str(int(time.time() if now is None else now))
    return {"issued_at": issued_at, "signature": _signature(metadata, key_bytes, issued_at, intent)}


def verify_dispatch(metadata: Mapping[str, Any], key: str, *, intent: str, now: float | None = None) -> None:
    """Reject missing, changed, expired, or future-dated execution contexts."""
    key_bytes = _key_bytes(key)
    diagnostic_reason = "MALFORMED_PROOF"
    try:
        proof = metadata[PROOF_KEY]
        issued_at = proof["issued_at"]
        if not isinstance(issued_at, str) or not issued_at.isascii() or not issued_at.isdecimal():
            raise ValueError("Invalid timestamp")
        signature = proof["signature"]
        if not isinstance(signature, str):
            raise ValueError("Invalid signature type")
        expected = _signature(metadata, key_bytes, issued_at, intent)
        diagnostic_reason = "INVALID_SIGNATURE"
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid signature")
        # Only attribute freshness failures to authenticated timestamps.
        diagnostic_reason = "MALFORMED_PROOF"
        issued_seconds = int(issued_at)
        current_time = time.time() if now is None else now
        if issued_seconds < current_time - MAX_AGE_SECONDS:
            diagnostic_reason = "EXPIRED_PROOF"
            raise ValueError("Expired proof")
        if issued_seconds > current_time + 30:
            diagnostic_reason = "FUTURE_PROOF"
            raise ValueError("Future proof")
    except (KeyError, TypeError, ValueError) as exc:
        raise DispatchValidationError("Untrusted role dispatch context", reason="UNTRUSTED_SOURCE",
                                      diagnostic_reason=diagnostic_reason) from exc

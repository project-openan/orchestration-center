# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Durable run state; every command is a short synchronous document UoW.

The lease fences local state, not external side effects. A persisted dispatch
attempt is never automatically sent again after owner loss.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from uuid import uuid4

from orchestrate.persistence.errors import StorageConflictError, StorageValidationError, StorageUnavailableError

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
#: Statuses that still hold an execution slot. ``reconciliation_required`` is
#: deliberately absent: its owner is gone, so it must not consume the budget.
ACTIVE_STATUSES = frozenset({"preparing", "dispatching", "running"})
RUN_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


class LeaseLost(StorageConflictError):
    """The caller may no longer publish results for this run."""


class CursorExpired(StorageConflictError):
    """The requested event history is no longer retained."""


class JobRepository:
    def __init__(self, documents, lease_seconds=30, max_active=16, event_limit=2000):
        self.documents = documents
        if not math.isfinite(float(lease_seconds)) or float(lease_seconds) < 1:
            raise ValueError("lease_seconds must be finite and at least one second")
        self.lease_seconds = float(lease_seconds)
        self.max_active = max(int(max_active), 1)
        self.event_limit = max(int(event_limit), 1)

    def _now(self):
        return float(self.documents.now())

    @staticmethod
    def _id(job_id):
        if not isinstance(job_id, str) or not RUN_ID.fullmatch(job_id):
            raise StorageValidationError("Invalid run identifier")
        return job_id

    @staticmethod
    def _allow(job, principal):
        # principal=None is reserved for internal worker operations.
        if principal is not None and job["principal"] != principal:
            return False
        return not job.get("deletion_requested", False)

    def submit(self, kind, request, principal, *, job_id=None, idempotency_key=None):
        if not principal or not isinstance(principal, str):
            raise StorageValidationError("A verified run principal is required")
        if kind not in {"execution", "sandbox"}:
            raise StorageValidationError("Unknown run kind")
        request_hash = hashlib.sha256(
            json.dumps(
                request.get("_idempotency_payload", request), sort_keys=True, allow_nan=False, ensure_ascii=False
            ).encode()
        ).hexdigest()
        key = None
        if idempotency_key is not None:
            if not 1 <= len(idempotency_key) <= 200:
                raise StorageValidationError("Idempotency-Key must contain 1..200 characters")
            key = hashlib.sha256(json.dumps([principal, kind, idempotency_key]).encode()).hexdigest()
        with self.documents.transaction():
            if key:
                old = self.documents.get("run_idempotency", key)
                if old:
                    if old["request_hash"] != request_hash:
                        raise StorageConflictError("Idempotency key was used with a different request")
                    found = self.documents.get("run_jobs", old["job_id"])
                    if found is None:
                        raise StorageConflictError("The idempotent run has expired")
                    return found
            if sum(j["status"] == "queued" and j["kind"] == kind for j in self.documents.list("run_jobs")) >= 128:
                raise StorageUnavailableError("Execution queue is full")
            job_id = self._id(job_id or uuid4().hex)
            now = self._now()
            job = dict(
                job_id=job_id,
                kind=kind,
                principal=principal,
                request=request,
                request_hash=request_hash,
                status="queued",
                owner=None,
                fence=0,
                lease_until=0,
                cancel_requested=False,
                deletion_requested=False,
                dispatch_attempt_id=None,
                last_seq=0,
                pruned_through_seq=0,
                created_at=now,
                updated_at=now,
                result=None,
                error=None,
            )
            self.documents.save("run_jobs", job_id, job, expected_revision=0)
            if key:
                self.documents.save(
                    "run_idempotency", key, dict(job_id=job_id, request_hash=request_hash), expected_revision=0
                )
            return job

    def get(self, job_id, principal=None):
        self._id(job_id)
        with self.documents.transaction():
            job = self.documents.get("run_jobs", job_id)
            return job if job and self._allow(job, principal) else None

    def list(self, principal=None, kind=None):
        with self.documents.transaction():
            return sorted(
                (
                    j
                    for j in self.documents.list("run_jobs")
                    if self._allow(j, principal) and (kind is None or j["kind"] == kind)
                ),
                key=lambda j: j["created_at"],
                reverse=True,
            )

    def claim(self, job_id, owner):
        self._id(job_id)
        with self.documents.transaction():
            job = self.documents.get("run_jobs", job_id)
            if not job or job["status"] != "queued" or job["cancel_requested"]:
                return None
            # Only statuses that still hold an execution slot are counted. A run
            # waiting for reconciliation has no live owner, so counting it would
            # let a few lost owners stall every later claim once the budget fills.
            active = sum(
                j["status"] in ACTIVE_STATUSES
                for j in self.documents.list("run_jobs")
                if j["kind"] == job["kind"]
            )
            if active >= self.max_active:
                return None
            job.update(
                status="preparing",
                owner=owner,
                fence=job["fence"] + 1,
                lease_until=self._now() + self.lease_seconds,
                updated_at=self._now(),
            )
            self.documents.save("run_jobs", job_id, job)
            return job

    def _owned(self, job_id, owner, fence):
        job = self.documents.get("run_jobs", self._id(job_id))
        if (
            not job
            or job["owner"] != owner
            or job["fence"] != fence
            or job["lease_until"] <= self._now()
            or job["status"] in TERMINAL
            or job["status"] == "reconciliation_required"
        ):
            raise LeaseLost("Run ownership expired")
        return job

    def renew(self, job_id, owner, fence):
        with self.documents.transaction():
            try:
                job = self._owned(job_id, owner, fence)
            except LeaseLost:
                return False
            job.update(lease_until=self._now() + self.lease_seconds, updated_at=self._now())
            self.documents.save("run_jobs", job_id, job)
            return True

    def _append(self, job, event):
        seq = job["last_seq"] + 1
        row = dict(job_id=job["job_id"], seq=seq, event=event)
        self.documents.save("run_events", f"{job['job_id']}-{seq:012d}", row, expected_revision=0)
        job["last_seq"] = seq
        if event.get("type") == "psop_update":
            job["current_psop"] = event.get("data", {}).get("psop")
        old_seq = seq - self.event_limit
        if old_seq > 0:
            self.documents.delete("run_events", f"{job['job_id']}-{old_seq:012d}")
            job["pruned_through_seq"] = old_seq
        job["updated_at"] = self._now()
        return row

    def append(self, job_id, owner, fence, event):
        with self.documents.transaction():
            job = self._owned(job_id, owner, fence)
            if event.get("type") == "resolution":
                job["resolution"] = event.get("data", {})
            if event.get("type") == "psop_update":
                job["execution_psop"] = event.get("data", {}).get("psop")
            if job["dispatch_attempt_id"] and event.get("type") not in {"start", "resolution"}:
                job["status"] = "running"
            row = self._append(job, event)
            self.documents.save("run_jobs", job_id, job)
            return row

    def mark_dispatch(self, job_id, owner, fence, envelope=None):
        with self.documents.transaction():
            job = self._owned(job_id, owner, fence)
            if job["cancel_requested"]:
                raise LeaseLost("Run was cancelled before dispatch")
            if job["dispatch_attempt_id"]:
                raise LeaseLost("A dispatch attempt already exists; reconcile instead")
            job["frozen_psop"] = job.get("execution_psop", job["request"].get("psop"))
            job["frozen_resolution"] = job.get("resolution")
            job.update(status="dispatching", dispatch_attempt_id=uuid4().hex, updated_at=self._now())
            if envelope is not None:
                job["dispatch_envelope"] = envelope
            self.documents.save("run_jobs", job_id, job)
            return job

    def observe_transport(self, job_id, owner, fence, transport):
        with self.documents.transaction():
            job = self._owned(job_id, owner, fence)
            if not job["dispatch_attempt_id"]:
                raise LeaseLost("Remote task has no persisted send intent")
            if job.get("host_task_id") not in (None, transport["task_id"]):
                raise StorageConflictError("Remote task identity changed")
            job.update(
                host_task_id=transport["task_id"],
                host_context_id=transport.get("context_id"),
                remote_state=transport.get("task_state"),
                status="running",
                updated_at=self._now(),
            )
            self.documents.save("run_jobs", job_id, job)

    def finish(self, job_id, owner, fence, status, result=None, error=None):
        if status not in TERMINAL | {"reconciliation_required"}:
            raise StorageValidationError("Invalid final run state")
        with self.documents.transaction():
            job = self._owned(job_id, owner, fence)
            job.update(status=status, result=result, error=error, updated_at=self._now())
            event = dict(type="run_status", data=dict(execution_id=job_id, status=status, error=error))
            self._append(job, event)
            self.documents.save("run_jobs", job_id, job)
            return job

    def cancel(self, job_id, principal):
        self._id(job_id)
        with self.documents.transaction():
            job = self.documents.get("run_jobs", job_id)
            if not job or not self._allow(job, principal):
                return None
            if job["status"] not in TERMINAL:
                job["cancel_requested"] = True
                if job["status"] == "reconciliation_required":
                    # No owner remains to observe the flag, so an explicit cancel
                    # is the operator's resolution of the unknown outcome.
                    job.update(status="cancelled", fence=job["fence"] + 1, lease_until=0)
                    self._append(job, dict(type="cancelled", data={"execution_id": job_id}))
                elif not job["dispatch_attempt_id"]:
                    # Fence any preparing owner before it can record a send intent.
                    job.update(status="cancelled", fence=job["fence"] + 1, lease_until=0)
                    self._append(job, dict(type="cancelled", data={"execution_id": job_id}))
                self.documents.save("run_jobs", job_id, job)
            return job

    def remove(self, job_id, principal):
        with self.documents.transaction():
            job = self.cancel(job_id, principal)
            if job is None:
                return False
            job["deletion_requested"] = True
            self.documents.save("run_jobs", job_id, job)
            return True

    def read_events(self, job_id, principal, after=0):
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise StorageValidationError("Invalid event cursor")
        with self.documents.transaction():
            job = self.documents.get("run_jobs", self._id(job_id))
            if not job or not self._allow(job, principal):
                return None, []
            if after < job["pruned_through_seq"] or after > job["last_seq"]:
                raise CursorExpired("Event cursor is outside the retained history; reload the snapshot")
            rows = []
            for seq in range(after + 1, min(job["last_seq"], after + 200) + 1):
                row = self.documents.get("run_events", f"{job_id}-{seq:012d}")
                if row is None:
                    raise CursorExpired("Event history has a gap; reload the snapshot")
                rows.append(row)
            return job, rows

    def observe_stale(self, job_id):
        with self.documents.transaction():
            job = self.documents.get("run_jobs", self._id(job_id))
            if (
                not job
                or job["status"] not in {"preparing", "dispatching", "running"}
                or job["lease_until"] > self._now()
            ):
                return job
            # Conservative: even preparation may already have frozen a role plan.
            # No automatic re-resolution or remote creation after owner loss.
            job.update(
                status="reconciliation_required",
                error="Execution owner lost; remote outcome requires reconciliation",
                fence=job["fence"] + 1,
                lease_until=0,
                updated_at=self._now(),
            )
            self._append(
                job, dict(type="run_status", data={"execution_id": job_id, "status": "reconciliation_required"})
            )
            self.documents.save("run_jobs", job_id, job)
            return job


def run_snapshot(job):
    """Public projection excludes credentials, request snapshots and raw cards."""
    keys = (
        "job_id",
        "kind",
        "status",
        "created_at",
        "updated_at",
        "cancel_requested",
        "deletion_requested",
        "result",
        "error",
    )
    return {
        **{k: job[k] for k in keys},
        "host_task_id": job.get("host_task_id"),
        "host_context_id": job.get("host_context_id"),
        "execution_id": job["job_id"],
        "psop": job.get("current_psop"),
        "as_of_seq": job["last_seq"],
        "events_pruned_through_seq": job["pruned_through_seq"],
    }

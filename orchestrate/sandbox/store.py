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

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrate.sandbox.models import SandboxRunReport, StubTemplate


class SandboxStore:
    """File-backed sandbox reports and workflow-scoped templates."""

    _ID_PATTERN = re.compile(r"^[\w\-]+$")

    def __init__(self, base_dir: str | Path | None = None, *,
                 max_report_bytes: int = 2_000_000, documents=None) -> None:
        if max_report_bytes < 1024:
            raise ValueError("max_report_bytes must be at least 1024")
        self.max_report_bytes = max_report_bytes
        from orchestrate.persistence.documents import FileDocuments, data_root
        base = Path(base_dir).resolve() if base_dir else data_root() / "workflow_storage" / "sandbox"
        self._custom = base_dir is not None
        self._injected = documents
        self._file_documents = FileDocuments(
            base, {"sandbox_reports": "reports",
                   "sandbox_templates": "templates"}) if base_dir else FileDocuments(data_root())
        self.report_dir = base / "reports"
        self.template_dir = base / "templates"


    @property
    def documents(self):
        if self._injected is not None:
            return self._injected
        if not self._custom:
            from orchestrate.persistence import current_context
            return current_context().documents
        return self._file_documents

    def save_report(
        self,
        report: SandboxRunReport,
        events: list[dict[str, Any]],
        *,
        status: str = "completed",
    ) -> str:
        payload = {
            "status": status,
            "report": report.model_dump(mode="json"),
            "events": events,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) > self.max_report_bytes:
            snapshot = payload["report"]
            payload["events"] = []
            snapshot["events_truncated"] = True
            snapshot["report_truncated"] = True
            for field in ("static_checks", "execution_path", "context_trace", "stub_interactions", "risks", "suggestions"):
                snapshot[field] = []
            if snapshot.get("error"):
                snapshot["error"] = str(snapshot["error"])[:1000]
            snapshot["workflow_name"] = str(snapshot["workflow_name"])[:256]
            if len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")) > self.max_report_bytes:
                raise ValueError("Sandbox report exceeds configured size limit")
        self._validate_id(report.verification_id)
        self.documents.save("sandbox_reports", report.verification_id, payload)
        return report.verification_id

    def load_report(self, verification_id: str) -> dict[str, Any] | None:
        if not self._ID_PATTERN.fullmatch(verification_id):
            return None
        return self.documents.get("sandbox_reports", verification_id)

    def delete_report(self, verification_id: str) -> bool:
        try:
            self._validate_id(verification_id)
        except ValueError:
            return False
        return self.documents.delete("sandbox_reports", verification_id)

    def list_reports(self) -> list[dict[str, Any]]:
        records = []
        for payload in reversed(self.documents.list("sandbox_reports")):
            report = payload.get("report", {})
            records.append({
                "verification_id": report.get("verification_id"),
                "workflow_id": report.get("workflow_id"), "workflow_name": report.get("workflow_name"),
                "mode": report.get("mode", "sandbox"), "scenario": report.get("scenario"),
                "verdict": report.get("verdict"), "status": payload.get("status", "completed"),
            })
        return records

    def save_templates(self, workflow_id: str, templates: list[StubTemplate]) -> int:
        self._validate_id(workflow_id)
        self.documents.save("sandbox_templates", workflow_id, {
            "workflow_id": workflow_id,
            "templates": [template.model_dump(mode="json") for template in templates],
        })
        return len(templates)

    def load_templates(self, workflow_id: str) -> list[StubTemplate]:
        self._validate_id(workflow_id)
        payload = self.documents.get("sandbox_templates", workflow_id)
        if payload is None:
            return []
        return [StubTemplate.model_validate(item) for item in payload.get("templates", [])]

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def _validate_id(cls, value: str) -> None:
        if not cls._ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid workflow identifier")

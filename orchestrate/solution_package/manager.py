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

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from loguru import logger

from orchestrate.persistence.documents import FileDocuments
from orchestrate.persistence.errors import StorageConflictError, StorageValidationError


class SolutionPackageManager:
    """Package records through the configured storage port; filenames stay API-compatible."""
    def __init__(self, storage_dir=None, *, documents=None, seed_on_init=True):
        project_root = Path(__file__).resolve().parents[2]
        from common.util.config_util import get_conf
        self.storage_dir = Path(storage_dir) if storage_dir else (
            Path(os.environ.get("ORCH_DATA_DIR")
             or get_conf().get("data_dir")
             or project_root / "data") / "solution_packages")
        self._default_storage_dir = self.storage_dir
        self.seed_dir = project_root / "samples" / "solution_packages"
        self._injected = documents
        self._custom = storage_dir is not None
        root = self.storage_dir.parent if self.storage_dir.name == "solution_packages" else self.storage_dir
        locations = None if self.storage_dir.name == "solution_packages" else {"solution_packages": "."}
        self._files = FileDocuments(root, locations)
        if storage_dir is None and seed_on_init:
            from common.util.persistence_mode import is_db_mode
            if not is_db_mode():
                self._seed_demo_packages()

    @property
    def documents(self):
        if self._injected is not None:
            return self._injected
        if not self._custom:
            from orchestrate.persistence import current_context
            context = current_context()
            if context.mode != "file":
                return context.documents
        root = self.storage_dir.parent if self.storage_dir.name == "solution_packages" else self.storage_dir
        locations = None if self.storage_dir.name == "solution_packages" else {"solution_packages": "."}
        if self._files.root != root.resolve():
            self._files = FileDocuments(root, locations)
        return self._files

    def _seed_demo_packages(self):
        if self.storage_dir != self._default_storage_dir or self._custom:
            return
        if os.environ.get("TESTING", "").lower() in ("true", "1", "yes"):
            return
        for path in sorted(self.seed_dir.glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            key = path.stem
            with self.documents.transaction():
                if self.documents.get("solution_packages", key) is None:
                    self.documents.save("solution_packages", key, value)

    @staticmethod
    def _key(filename):
        if (not isinstance(filename, str) or not filename
            or Path(filename).name != filename or any(c in filename for c in "/\\")):
            raise StorageValidationError("Invalid package filename")
        return Path(filename).stem

    def _get_storage_path(self, pdf_filename):
        return self.storage_dir / (self._key(pdf_filename) + ".json")

    def store_solution_package(self, pdf_filename, chapters_dict):
        key = self._key(pdf_filename)
        with self.documents.transaction():
            old = self.documents.get("solution_packages", key)
            if old and old.get("pdf_filename") != pdf_filename:
                raise StorageConflictError("Package filename collides with another package")
            value = {
                "package_id": (old or {}).get("package_id", str(uuid5(NAMESPACE_URL, pdf_filename))),
                "pdf_filename": pdf_filename, "chapters": chapters_dict,
                "content_hash": hashlib.sha256(
                    json.dumps(chapters_dict, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                "chapter_count": len(chapters_dict), "chapter_titles": list(chapters_dict),
                "created_at": (old or {}).get("created_at", datetime.now(timezone.utc).isoformat()),
            }
            # Re-parsing the same PDF replaces the chapter content, not the
            # workflows already generated from an earlier parse; otherwise a
            # parse that never reaches generation would silently drop links.
            for link_key in ("workflow_id", "workflow_ids", "workflow_bindings"):
                if old and link_key in old:
                    value[link_key] = old[link_key]
            self.documents.save("solution_packages", key, value)
        return True

    def retrieve_by_filename(self, pdf_filename):
        value = self.documents.get("solution_packages", self._key(pdf_filename))
        if value and value.get("pdf_filename") != pdf_filename:
            return None
        return value

    def retrieve_all(self):
        return self.documents.list("solution_packages")

    def source_revision(self, pdf_filename):
        # An arbitrary PreFlow title need not name a package, and a title may carry
        # characters the document port rejects; both simply mean "no source".
        try:
            key = self._key(pdf_filename)
            with self.documents.transaction():
                if self.retrieve_by_filename(pdf_filename) is None:
                    return None
                return self.documents.revision("solution_packages", key)
        except StorageValidationError:
            return None

    def link_workflow(self, pdf_filename, workflow_id, binding="instance", expected_revision=None):
        if binding not in ("role", "instance"):
            logger.error(f"Unknown workflow binding '{binding}' for solution package '{pdf_filename}'")
            return False
        try:
            key = self._key(pdf_filename)
        except StorageValidationError:
            logger.warning(f"Skipping package link for unusable name {pdf_filename!r}")
            return False
        with self.documents.transaction():
            if (expected_revision is not None
                    and self.documents.revision("solution_packages", key) != expected_revision):
                raise StorageConflictError("Source solution package changed during workflow generation")
            value = self.retrieve_by_filename(pdf_filename)
            if value is None:
                return False
            value["workflow_id"] = workflow_id
            links = value.setdefault("workflow_ids", [])
            if workflow_id not in links:
                links.append(workflow_id)
            # Role-catalog and instance workflows occupy separate slots so
            # generating one never hides the other (REQ74).
            bindings = value.get("workflow_bindings")
            if not isinstance(bindings, dict):
                bindings = {}
            bindings[binding] = workflow_id
            value["workflow_bindings"] = bindings
            self.documents.save("solution_packages", self._key(pdf_filename), value)
        return True

    def get_all_filenames(self):
        return [value["pdf_filename"] for value in self.retrieve_all() if "pdf_filename" in value]

    def delete_by_filename(self, pdf_filename):
        with self.documents.transaction():
            if self.retrieve_by_filename(pdf_filename) is None:
                return False
            return self.documents.delete("solution_packages", self._key(pdf_filename))

    def get_chapter_content(self, pdf_filename, chapter_title):
        value = self.retrieve_by_filename(pdf_filename)
        return value.get("chapters", {}).get(chapter_title) if value else None

    def search_chapters_by_keyword(self, keyword):
        results = []
        for package in self.retrieve_all():
            chapters = {key: value for key, value in package.get("chapters", {}).items()
                        if keyword.lower() in value.lower()}
            if chapters:
                results.append({"pdf_filename": package.get("pdf_filename", ""),
                                "matching_chapters": chapters, "match_count": len(chapters)})
        return results

    def get_storage_stats(self):
        packages = self.retrieve_all()
        return {"storage_directory": str(self.storage_dir), "total_packages": len(packages),
                "total_chapters": sum(value.get("chapter_count", 0) for value in packages),
                "package_filenames": [value.get("pdf_filename", "") for value in packages]}

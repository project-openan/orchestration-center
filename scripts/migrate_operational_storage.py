# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Explicit, offline migration of legacy operational JSON; never deletes its source.

Stop file-mode writers first. Dry-run never initializes or writes the target.
"""

import argparse
import hashlib
import json
from pathlib import Path

from orchestrate.persistence.documents import FileDocuments, _LOCATIONS
from orchestrate.persistence.errors import StorageConflictError, StorageCorruptionError

NAMESPACES = ("preflows", "solution_packages", "sandbox_reports", "sandbox_templates")


def migrate(source_root, target, *, target_identity, dry_run=False):
    source = FileDocuments(source_root)
    result = {"dry_run": dry_run, "imported": 0, "verified": 0, "planned": 0}
    # Capture a consistent immutable source plan; the process lock remains held.
    plan = []
    with source.transaction():
        for namespace in NAMESPACES:
            directory = Path(source_root) / _LOCATIONS[namespace]
            for path in sorted(directory.glob("*.json")):
                payload = source.get(namespace, path.stem)
                if not isinstance(payload, dict):
                    raise StorageCorruptionError("Invalid legacy document")
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                plan.append((namespace, path.stem, payload, digest))
    if dry_run:
        result["planned"] = len(plan)
        return result
    for namespace, key, payload, digest in plan:
        checkpoint = hashlib.sha256(json.dumps([namespace, key, digest, target_identity, 1]).encode()).hexdigest()
        with target.transaction():
            existing = target.get(namespace, key)
            if existing is not None and existing != payload:
                raise StorageConflictError(f"Target differs: {namespace}/{key}")
            if existing is None:
                target.save(namespace, key, payload)
                result["imported"] += 1
            else:
                result["verified"] += 1
            target.save(
                "storage_migrations",
                checkpoint,
                {
                    "namespace": namespace,
                    "key": key,
                    "input_hash": digest,
                    "target_identity": target_identity,
                    "version": 1,
                    "workspace": "legacy-shared-workspace",
                },
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--mode", choices=("mysql", "postgresql"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--initialize", action="store_true", help="Run schema initialization once before starting replicas"
    )
    args = parser.parse_args()
    source = Path(args.source_root).resolve()
    if not source.is_dir():
        parser.error("Source directory does not exist")
    if args.dry_run:
        print(json.dumps(migrate(source, None, target_identity="dry-run", dry_run=True)))
        return
    from orchestrate.persistence.factory import create

    backend = create(args.mode, {"deployment_mode": "single"})
    try:
        if args.initialize:
            backend.initialize()
        else:
            backend.documents().check_ready()
        c = backend._provider.config
        # Nonsecret identity, not the password or complete connection profile.
        identity = hashlib.sha256(
            json.dumps([args.mode, c.get("host"), c.get("port"), c.get("database")]).encode()
        ).hexdigest()
        print(json.dumps(migrate(source, backend.documents(), target_identity=identity)))
    finally:
        backend.close()


if __name__ == "__main__":
    main()

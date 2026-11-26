# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in migration of known, unedited wrong-domain default workflows.

Stop workflow editing/execution before --apply. Default invocation previews
only. Seeding never overwrites installed data; this tool requires an exact old
document fingerprint and retains a backup before each verified replacement.
"""

import argparse
import hashlib
import json
from pathlib import Path

from database.utils.seed_data import SEED_DATA_DIR
from orchestrate.core.model.psop import PSOP
from orchestrate.persistence import build_context

PREVIOUS_FINGERPRINTS = {
    'IG1502A_AN_L4_Individual_Mobile_Service_Delivery_Solution_Package':
        '60bce5c3e7cda4c972ef6c67836d01f53a94fd60c5c179c6d6ad7d4501c3e87c',
    'IG1505G_AN_L4_Computing_Network_FaultManagement_SolutionPackage':
        '3687344d15405d79ade0193e65da86e40e6939c7c255fa0c04f6366e0648a07e',
    'IG1523B_AN_L4_Core_Network_Fault_Management_Solution_Package':
        '19c90f289f87c787247a8e5837dc5267e8634a8c14be99a45d5ff25c1fd8e272',
    'IG1525E_AN_L4_IP_Network_Quality_Optimization_Solution_Package':
        '5cbe9cdba9938c8694fbe2eca50aeded026c2619b83bf0603dbc3ad8b9216558',
    'IG1501C_AN_L4_IP_Network_Fault_Management_Solution_Package':
        'aec8cce1aaa008503a3f7d06b057e15c607e3e4eb38c93d3fceef00378c8f0a5',
    'IG1523E_AN_L4_IP_Network_Fault_Management_Solution_Package':
        '744277acc844117a43af70b2ef789d9fb4466e51023fc3cf50121f9ac623fb5d',
    'IG1523D_AN_L4_Transport_Network_Fault_Management_Solution_Package':
        'f919f8e63fdccf5582702ad10a692e5c8e44d1e061a09f4f4b104fc9255a4ae6',
}


def fingerprint(psop: PSOP) -> str:
    content = json.dumps(psop.model_dump(mode='json'), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def migrate(repository, *, apply: bool = False, backup_dir: Path) -> list[dict]:
    """Replace only exact old defaults; missing, current and edited rows stay intact."""
    results = []
    for name, previous in PREVIOUS_FINGERPRINTS.items():
        replacement = PSOP.model_validate_json((SEED_DATA_DIR / f'{name}.json').read_text(encoding='utf-8'))
        current = repository.get(replacement.id)
        status = 'missing' if current is None else 'conflict'
        if current == replacement:
            status = 'current'
        elif current is not None and fingerprint(current) == previous:
            status = 'eligible'
            if apply:
                backup_dir.mkdir(parents=True, exist_ok=True)
                path = backup_dir / f'{replacement.id}.json'
                if path.exists():
                    if PSOP.model_validate_json(path.read_text(encoding='utf-8')) != current:
                        raise RuntimeError('Existing backup differs; choose another backup directory')
                else:
                    with path.open('x', encoding='utf-8') as stream:
                        stream.write(current.model_dump_json(indent=2))
                if repository.get(replacement.id) != current:
                    raise RuntimeError('Workflow changed during migration; stop concurrent editing first')
                if repository.save(replacement) != replacement.id or repository.get(replacement.id) != replacement:
                    raise RuntimeError('Migrated workflow could not be verified; backup retained')
                status = 'updated'
        results.append({'workflow_id': replacement.id, 'name': name, 'status': status})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write after stopping concurrent editing/execution')
    parser.add_argument('--backup-dir', type=Path, default=Path('data/seed_migration_backups/2026-10-19'))
    args = parser.parse_args()
    context = build_context()
    try:
        context.check_ready()
        rows = migrate(context.psops, apply=args.apply, backup_dir=args.backup_dir)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 1 if any(row['status'] == 'conflict' for row in rows) else 0
    finally:
        context.close()


if __name__ == '__main__':
    raise SystemExit(main())

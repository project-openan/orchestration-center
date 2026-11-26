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
Default (seed) data import for the orchestration center database.

Ships the 19 pre-orchestrated AN L4 SPG workflows as repository resources so
that a fresh installation starts with a usable workflow library:

    database/seed_data/psop/*.json   # one PSOP workflow per file

Seeding happens automatically at installation/startup:
    database.utils.table_creation.create_tables() -> seed_default_psops()          # database modes
    orchestrate.persistence.file_backend.FileStorageBackend.initialize()
        -> seed_default_psops_to_file_storage()                                    # file mode

The import is idempotent and non-destructive: rows whose id already exists in
the psop table are left untouched (ON CONFLICT DO NOTHING), and existing
workflow storage files are never overwritten, so user edits made through the
designer or the API are never overwritten by re-seeding.

Manual import (optional, e.g. for custom install scripts):

    python -m database.utils.seed_data
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

from common.util.config_util import get_root_path
from common.util.persistence_mode import persistence_mode
from orchestrate.core.model.psop import PSOP

SEED_DATA_DIR = Path(get_root_path()) / "database" / "seed_data" / "psop"

INSERT_SEED_PSOP_SQL = """
    INSERT INTO psop (id, name, description, psop_content)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (id) DO NOTHING
"""
INSERT_SEED_PSOP_MYSQL_SQL = """
    INSERT INTO psop (id, name, description, psop_content)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE id = id
"""

TESTING_ENV = "TESTING"


def _testing_mode() -> bool:
    """True when the process is running the test suite.

    Seeding is deployment-time behavior: the live integration tests create
    their own throwaway databases and assert exact row counts, so the default
    data must never be injected there (same convention as the solution
    package manager).
    """
    return os.environ.get(TESTING_ENV, "").lower() in ("true", "1", "yes")


def list_seed_files(seed_dir: Path = SEED_DATA_DIR) -> List[Path]:
    """Return the seed PSOP JSON files shipped with the repository."""
    if not seed_dir.is_dir():
        return []
    return sorted(seed_dir.glob("*.json"))


def _load_seed_record(path: Path) -> Tuple[Dict[str, str], PSOP]:
    """Load and validate one seed file. Returns (row, psop) or raises."""
    with open(path, "r", encoding="utf-8") as f:
        content = json.load(f)
    psop = PSOP.model_validate(content)  # fail fast on corrupt seed data
    row = {
        "id": psop.id,
        "name": psop.name,
        "description": psop.description or "",
        "psop_content": json.dumps(content, ensure_ascii=False),
    }
    return row, psop


def seed_default_psops(seed_dir: Path = SEED_DATA_DIR) -> int:
    """Import the default PSOP workflows into the database.

    Only inserts rows whose id is not present yet, so re-running against an
    existing installation is a no-op. Returns the number of rows inserted.

    Raises RuntimeError when the database is unreachable.
    """
    seed_files = list_seed_files(seed_dir)
    if not seed_files:
        logger.warning(f"No seed PSOP files found in {seed_dir} - skipping default data import")
        return 0
    if _testing_mode():
        logger.info("TESTING mode: skipping default data seeding")
        return 0
    from database.utils.db_connection import create_connection
    insert_sql = INSERT_SEED_PSOP_MYSQL_SQL if persistence_mode() == 'mysql' else INSERT_SEED_PSOP_SQL
    conn = create_connection()
    if conn is None:
        raise RuntimeError("Unable to connect to database; default data not imported")
    inserted = 0
    skipped = 0
    try:
        for path in seed_files:
            try:
                row, psop = _load_seed_record(path)
            except Exception as e:
                logger.error(f"Skipping invalid seed file {path.name}: {e}")
                skipped += 1
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        insert_sql,
                        (row["id"], row["name"], row["description"], row["psop_content"]),
                    )
                    was_inserted = cur.rowcount > 0
                conn.commit()
                if was_inserted:
                    inserted += 1
                    logger.info(f"Imported default workflow '{psop.name}' (id={psop.id})")
                else:
                    skipped += 1
            except Exception as e:
                # A PostgreSQL error aborts the transaction. Roll back this
                # seed before attempting the next, never report rolled-back
                # earlier seeds as successfully imported.
                conn.rollback()
                logger.error(f"Unexpected error importing seed '{path.name}': {e}")
                skipped += 1
    finally:
        conn.close()

    logger.info(
        f"Default data import finished: {inserted} imported, "
        f"{skipped} already present or skipped, out of {len(seed_files)} seed files"
    )
    return inserted


def seed_default_psops_to_file_storage(seed_dir: Path = SEED_DATA_DIR, target_dir: Optional[Path] = None) -> int:
    """Materialize the default PSOP workflows into file-based workflow storage.

    File persistence mode (`persistence_mode=file`) never touches the
    database, so without this step a default deployment has an empty workflow
    library even though the seed files ship with the repository. Copies each
    seed file to <target>/<psop_id>.json, leaving existing files untouched
    (user edits are never overwritten). Returns the number of files copied.
    """
    seed_files = list_seed_files(seed_dir)
    if not seed_files:
        logger.warning(f"No seed PSOP files found in {seed_dir} - skipping file storage seeding")
        return 0
    if _testing_mode():
        logger.info("TESTING mode: skipping file storage seeding")
        return 0
    if target_dir is None:
        target_dir = Path(get_root_path()) / "data" / "workflow_storage" / "psop"
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in seed_files:
        try:
            _, psop = _load_seed_record(path)
        except Exception as e:
            logger.error(f"Skipping invalid seed file {path.name}: {e}")
            continue
        target = target_dir / f"{psop.id}.json"
        if target.exists():
            continue
        shutil.copyfile(path, target)
        copied += 1
        logger.info(f"Seeded default workflow into file storage: '{psop.name}' (id={psop.id})")
    if copied:
        logger.info(f"Default file-storage seeding finished: {copied} workflow(s) copied into {target_dir}")
    return copied


if __name__ == "__main__":
    count = seed_default_psops()
    logger.info(f"seed_default_psops inserted {count} workflow(s)")

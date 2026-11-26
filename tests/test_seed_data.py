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

"""Tests for the default-data seeders: file-storage materialization of the
default PSOP workflows (file persistence mode) and idempotency guarantees."""

import json
from pathlib import Path

import pytest

from database.utils.seed_data import (
    list_seed_files,
    seed_default_psops_to_file_storage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SEEDS = REPO_ROOT / "database" / "seed_data" / "psop"


@pytest.fixture(autouse=True)
def _allow_seeding(monkeypatch):
    """The seeders refuse to run under TESTING; these are unit tests of the
    seeder itself, so switch the gate off."""
    monkeypatch.delenv("TESTING", raising=False)


def _minimal_psop(psop_id: str, name: str) -> dict:
    return {
        "id": psop_id,
        "name": name,
        "description": f"default workflow {name}",
        "created_at": "2026-10-15T08:00:00+00:00",
        "steps": [],
    }


@pytest.fixture
def seed_dir(tmp_path):
    """A seed directory with two valid PSOP files and one corrupt file."""
    directory = tmp_path / "seeds"
    directory.mkdir()
    (directory / "a.json").write_text(
        json.dumps(_minimal_psop("seed-id-a", "Workflow A"), ensure_ascii=False), encoding="utf-8"
    )
    (directory / "b.json").write_text(
        json.dumps(_minimal_psop("seed-id-b", "Workflow B"), ensure_ascii=False), encoding="utf-8"
    )
    (directory / "broken.json").write_text("{not json", encoding="utf-8")
    return directory


class TestSeedDefaultPsopsToFileStorage:
    def test_copies_valid_seeds_and_skips_corrupt_ones(self, seed_dir, tmp_path):
        target = tmp_path / "workflow_storage" / "psop"
        copied = seed_default_psops_to_file_storage(seed_dir=seed_dir, target_dir=target)

        assert copied == 2
        assert (target / "seed-id-a.json").is_file()
        assert (target / "seed-id-b.json").is_file()
        # the corrupt seed must not produce a file named after the broken file
        assert not (target / "broken.json").exists()
        assert json.loads((target / "seed-id-a.json").read_text(encoding="utf-8"))["name"] == "Workflow A"

    def test_never_overwrites_existing_workflow_files(self, seed_dir, tmp_path):
        target = tmp_path / "workflow_storage" / "psop"
        target.mkdir(parents=True)
        user_edit = json.dumps(_minimal_psop("seed-id-a", "User Edited A"), ensure_ascii=False)
        (target / "seed-id-a.json").write_text(user_edit, encoding="utf-8")

        copied = seed_default_psops_to_file_storage(seed_dir=seed_dir, target_dir=target)

        assert copied == 1  # only workflow B is new
        assert json.loads((target / "seed-id-a.json").read_text(encoding="utf-8"))["name"] == "User Edited A"
        assert (target / "seed-id-b.json").is_file()

    def test_fully_idempotent(self, seed_dir, tmp_path):
        target = tmp_path / "workflow_storage" / "psop"
        first = seed_default_psops_to_file_storage(seed_dir=seed_dir, target_dir=target)
        second = seed_default_psops_to_file_storage(seed_dir=seed_dir, target_dir=target)

        assert first == 2
        assert second == 0

    def test_empty_seed_dir_is_a_noop(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        target = tmp_path / "workflow_storage" / "psop"

        assert seed_default_psops_to_file_storage(seed_dir=empty, target_dir=target) == 0
        assert not target.exists()

    def test_shipped_seed_library_is_complete(self):
        """The repository ships the default workflow library; every seed file
        must parse as a PSOP so a fresh install can never import garbage."""
        seeds = list_seed_files(SHIPPED_SEEDS)
        assert len(seeds) == 19
        ids = set()
        for path in seeds:
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["id"], f"seed without id: {path.name}"
            assert record["name"], f"seed without name: {path.name}"
            assert record["steps"], f"seed without steps: {path.name}"
            ids.add(record["id"])
        assert len(ids) == 19, "seed workflow ids must be unique"


@pytest.mark.parametrize('mode,clause', [('mysql', 'ON DUPLICATE KEY UPDATE id = id'), ('postgresql', 'ON CONFLICT (id) DO NOTHING')])
def test_sql_seed_uses_idempotent_dialect_and_keeps_going_after_rollback(seed_dir, monkeypatch, mode, clause):
    from unittest.mock import MagicMock
    from database.utils import seed_data
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.rowcount = 1
    connection.commit.side_effect = [OSError('synthetic commit failure'), None]
    monkeypatch.setattr('database.utils.db_connection.create_connection', lambda: connection)
    monkeypatch.setattr(seed_data, 'persistence_mode', lambda: mode)
    assert seed_data.seed_default_psops(seed_dir) == 1
    assert connection.rollback.call_count == 1
    assert connection.commit.call_count == 2
    sql = connection.cursor.return_value.__enter__.return_value.execute.call_args.args[0]
    assert clause in sql
    connection.close.assert_called_once()


def test_mysql_table_creation_reaches_default_seed(monkeypatch):
    from unittest.mock import MagicMock
    from database.utils import table_creation
    seed, backend = MagicMock(), MagicMock()
    monkeypatch.setattr(table_creation, 'persistence_mode', lambda: 'mysql')
    monkeypatch.setattr('database.utils.mysql_connection.get_backend', lambda: backend)
    monkeypatch.setattr(table_creation, 'seed_default_psops', seed)
    table_creation.create_tables()
    backend.create_tables.assert_called_once()
    seed.assert_called_once()


def test_file_backend_seeds_its_own_injected_directory(tmp_path, monkeypatch):
    from orchestrate.core.persistence import WorkflowStorage
    from orchestrate.persistence.file_backend import FilePersistenceBackend
    storage = WorkflowStorage(str(tmp_path))
    backend = FilePersistenceBackend(storage=storage)
    backend.initialize()
    assert len(storage.list_psops()) == 19
    assert all(storage.load_psop(workflow_id) for workflow_id in storage.list_psops())

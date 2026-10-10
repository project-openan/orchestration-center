# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Container persistence-mode bridge and credential materialization contracts."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX container entrypoint")
SCRIPT = Path(__file__).resolve().parents[1] / "docker-entrypoint.sh"


def _environment(tmp_path):
    (tmp_path / "etc/conf").mkdir(parents=True)
    (tmp_path / "etc/conf/server.conf").write_text("persistence_mode=file\n")
    return {"APP_HOME": str(tmp_path), "PATH": os.environ["PATH"]}


def test_mysql_entrypoint_sets_mode_without_writing_password(tmp_path):
    env = _environment(tmp_path)
    env.update(PERSISTENCE_MODE="mysql", MYSQL_HOST="db", MYSQL_USER="tester",
               MYSQL_PASSWORD="quoted'password\"with$symbols")
    result = subprocess.run(["bash", str(SCRIPT), "true"], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "etc/conf/server.conf").read_text() == "persistence_mode=file\n"
    assert not (tmp_path / "etc/conf/mysql_config.json").exists()
    assert not (tmp_path / "etc/conf/db_config.json").exists()
    assert env["MYSQL_PASSWORD"] not in result.stdout + result.stderr


def test_postgres_environment_bridge_does_not_require_baked_in_secret_file(tmp_path):
    env = _environment(tmp_path)
    env.update(PERSISTENCE_MODE="postgresql", DB_HOST="db", DB_PORT="5432",
               DB_NAME="orchestration_center", DB_USERNAME="tester", DB_PASSWORD="quoted'password\"")
    result = subprocess.run(["bash", str(SCRIPT), "true"], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "etc/conf/db_config.json").exists()
    assert not (tmp_path / "etc/conf/db/postgresql.json").exists()
    assert env["DB_PASSWORD"] not in result.stdout + result.stderr

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
import re
from pathlib import Path

import psycopg2
from loguru import logger
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from common.util.config_util import get_root_path


DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def validate_database_name(name: str) -> str:
    if not DATABASE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid database name: '{name}'. Must match ^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    return name


def read_db_config(file_name):
    dir_path = Path(get_root_path()) / "etc" / "conf"
    file_path = dir_path / file_name
    with open(file_path, "r", encoding='utf-8') as f:
        return json.load(f)


conn_info = None


def _ensure_conn_info():
    global conn_info
    if conn_info is None:
        conn_info = read_db_config("db_config.json")
        validate_database_name(conn_info.get('database', "orchestration_center"))
    return conn_info


def create_database_if_not_exists():
    conn_info = _ensure_conn_info()
    default_conn_info = {**conn_info,  "database": "postgres"}
    try:
        conn = psycopg2.connect(**default_conn_info)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        database_name = conn_info.get('database', "orchestration_center")
        cursor.execute(
            sql.SQL("SELECT 1 FROM pg_database WHERE datname = {}").format(
                sql.Literal(database_name)
            )
        )
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(database_name)
                )
            )
            logger.info(f"Database {database_name} created successfully")

        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        return False

def create_connection():
    try:
        if not create_database_if_not_exists():
            return None
        conn_info = _ensure_conn_info()
        conn = psycopg2.connect(**conn_info)
        logger.info(f"Connected to database '{conn_info.get('database', 'unknown')}' on {conn_info.get('host', 'localhost')}:{conn_info.get('port', 5432)}")
        return conn
    except Exception as e:
        logger.error(f"Unable to connect to database: {e}")
        return None

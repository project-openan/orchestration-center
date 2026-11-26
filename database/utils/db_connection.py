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

import re
import threading

import psycopg2
from loguru import logger
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from common.util.config_util import get_root_path
from common.util.persistence_mode import persistence_mode

DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

def validate_database_name(name: str) -> str:
    if not DATABASE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid database name: '{name}'. Must match ^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    return name

def read_db_config(file_name):
    """Kept for call sites that still import this module; filenames from before
    etc/conf/db are not runtime sources."""
    from database.utils.connection_config import load_connection_config
    if file_name not in {"db_config.json", "postgresql.json"}:
        raise ValueError("Unsupported PostgreSQL config filename")
    return load_connection_config("postgresql", get_root_path())

class _ConnInfoHolder:
    """Thread-safe lazy holder for database connection info."""
    _instance: dict | None = None

    @classmethod
    def get(cls) -> dict:
        if cls._instance is None:
            cls._instance = read_db_config("db_config.json")
            validate_database_name(cls._instance.get('database', "orchestration_center"))
        return cls._instance

# create_connection() is called on every /rest/v1/orchestrate/* request
# (via is_auth_enabled() -> has_any_user()), so create_database_if_not_exists()
# would otherwise open a second, throwaway connection to the `postgres`
# maintenance database on every single request. The database's existence
# only needs confirming once per process -- it doesn't spontaneously
# disappear -- so cache a successful check (see #40).
_database_verified = False
_database_verified_lock = threading.Lock()

def create_database_if_not_exists():
    global _database_verified
    if _database_verified:
        return True
    with _database_verified_lock:
        if _database_verified:
            return True
        conn_info = _ConnInfoHolder.get()
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
            _database_verified = True
            return True
        except Exception as e:
            logger.error(f"Failed to create database: {e}")
            return False

def create_connection():
    try:
        from database.utils.connection_provider import current_provider
        provider = current_provider()
        if provider is not None:
            from orchestrate.persistence.documents import bound_sql_connection
            return bound_sql_connection(provider) or provider.connection()
        if persistence_mode() == "mysql":
            from database.utils.mysql_connection import get_backend
            return get_backend().connection()
        if not create_database_if_not_exists():
            return None
        conn_info = _ConnInfoHolder.get()
        conn = psycopg2.connect(**conn_info)
        logger.info(
            f"Connected to database '{conn_info.get('database', 'unknown')}' "
                f"on {conn_info.get('host', 'localhost')}:{conn_info.get('port', 5432)}")
        return conn
    except ValueError:
        # Config errors must fail loudly, without embedding driver/config values.
        raise
    except Exception:
        logger.error("Unable to connect to database")
        return None


def close_database():
    """Release MySQL pool resources; PostgreSQL connections close per operation."""
    from database.utils.mysql_connection import close_backend
    close_backend()

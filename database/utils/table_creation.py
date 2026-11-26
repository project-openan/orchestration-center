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

from database.utils.db_connection import create_connection
from database.utils.query_execution import execute_query
from database.utils.seed_data import seed_default_psops
from loguru import logger
from common.util.persistence_mode import persistence_mode


def create_tables():
    if persistence_mode() == "mysql":
        from database.utils.mysql_connection import get_backend
        get_backend().create_tables()
        _seed_defaults()
        return
    create_psop_sql = """
                       CREATE TABLE IF NOT EXISTS psop
                       (
                            id           VARCHAR(1024) PRIMARY KEY,
                            name         VARCHAR(1024) NOT NULL,
                            description  VARCHAR(1024),
                            psop_content    TEXT
                       )
                       """
    create_execution_record_sql = """
                       CREATE TABLE IF NOT EXISTS execution_records
                       (
                            execution_id    VARCHAR(64) PRIMARY KEY,
                            psop_id         VARCHAR(64) NOT NULL,
                            psop_name       VARCHAR(1024),
                            started_at      TIMESTAMP,
                            completed_at    TIMESTAMP,
                            status          VARCHAR(32),
                            step_count      INTEGER DEFAULT 0,
                            record_content  TEXT
                       )
                       """
    create_users_sql = """
                       CREATE TABLE IF NOT EXISTS users
                       (
                            id            SERIAL PRIMARY KEY,
                            username      VARCHAR(64) UNIQUE NOT NULL,
                            password_hash VARCHAR(128) NOT NULL,
                            salt          VARCHAR(64) NOT NULL,
                            role          VARCHAR(16) DEFAULT 'user',
                            must_change_password BOOLEAN DEFAULT FALSE,
                            password_scheme VARCHAR(16) DEFAULT 'legacy',
                            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                       )
                       """
    # CREATE TABLE IF NOT EXISTS above does not alter an existing table, so
    # installs that already have a `users` table from before these columns
    # existed need an explicit migration. Existing rows correctly default
    # password_scheme to 'legacy' -- see user_store.authenticate_user() for
    # what that means.
    migrate_users_must_change_password_sql = """
                       ALTER TABLE users
                       ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE
                       """
    migrate_users_password_scheme_sql = """
                       ALTER TABLE users
                       ADD COLUMN IF NOT EXISTS password_scheme VARCHAR(16) DEFAULT 'legacy'
                       """
    conn = create_connection()
    if conn is None:
        raise RuntimeError("Unable to create database connection; tables not created")
    try:
        _, err1 = execute_query(conn, create_psop_sql)
        if err1:
            raise RuntimeError(f"Failed to create psop table: {err1}")
        _, err2 = execute_query(conn, create_execution_record_sql)
        if err2:
            raise RuntimeError(f"Failed to create execution_records table: {err2}")
        _, err3 = execute_query(conn, create_users_sql)
        if err3:
            raise RuntimeError(f"Failed to create users table: {err3}")
        _, err4 = execute_query(conn, migrate_users_must_change_password_sql)
        if err4:
            raise RuntimeError(f"Failed to migrate users table (must_change_password): {err4}")
        _, err5 = execute_query(conn, migrate_users_password_scheme_sql)
        if err5:
            raise RuntimeError(f"Failed to migrate users table (password_scheme): {err5}")
        logger.info("Database tables verified/created: psop, execution_records, users")
    finally:
        conn.close()
    _seed_defaults()


def _seed_defaults():
    try:
        # Installation phase: import the shipped default SPG workflows so a
        # fresh deployment starts with a usable workflow library. Idempotent -
        # rows that already exist are never overwritten.
        seed_default_psops()
    except Exception as e:
        # Default data must never block the installation/startup itself.
        logger.error(f"Default data import failed (non-blocking): {e}")

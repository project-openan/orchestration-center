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
from loguru import logger


def create_tables():
    create_psop_sql = """
                       CREATE TABLE IF NOT EXISTS psop
                       (
                            id           VARCHAR(1024) PRIMARY KEY, -- Primary key ID
                            name         VARCHAR(1024) NOT NULL,    -- Name, cannot be null
                            description  VARCHAR(1024),                     -- Description
                            psop_content    TEXT             -- TEXT type suitable for long text
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
        logger.info("Database tables verified/created: psop, execution_records")
    finally:
        conn.close()

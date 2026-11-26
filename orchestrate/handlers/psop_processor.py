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

from loguru import logger

from database.utils.db_connection import create_connection
from database.utils.query_execution import execute_query
from database.utils.sql_dialect import upsert_sql
from database.utils.storage_errors import require_connection, raise_storage_error, close_resource
from orchestrate.persistence.errors import StorageCorruptionError
from orchestrate.core.model.psop import PSOP
from orchestrate.core.task_summary import build_tasks_summary, generation_binding  # noqa: F401  re-exported for existing callers
from orchestrate.core.workflow_search_result import WorkflowSearchResult


def custom_save_psop(psop):
    save_sql = upsert_sql("psop", "id", ("id", "name", "description", "psop_content"))
    conn = require_connection(create_connection())
    try:
        _, error = execute_query(conn, save_sql, (psop.id, psop.name, psop.description, psop.model_dump_json()))
        if error:
            raise_storage_error(error, "Failed to save PSOP")
        logger.info(f"[DB] PSOP saved: '{psop.name}' (id={psop.id})")
        return psop.id
    finally:
        close_resource(conn)


def custom_delete_psop(workflow_id):
    delete_sql = "DELETE FROM psop WHERE id = %s"
    conn = require_connection(create_connection())
    try:
        cur = conn.cursor()
        try:
            cur.execute(delete_sql, (workflow_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"[DB] PSOP deleted (id={workflow_id})")
            else:
                logger.warning(f"[DB] PSOP not found for deletion (id={workflow_id})")
            return deleted
        finally:
            close_resource(cur)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logger.warning("[DB] Rollback failed while deleting PSOP")
        raise_storage_error(e, "Failed to delete PSOP")
    finally:
        close_resource(conn)


def get_all_psops():
    query_sql = "SELECT psop_content FROM psop"
    conn = require_connection(create_connection())
    try:
        psops, error = execute_query(conn, query_sql)
        if error:
            raise_storage_error(error, "Failed to list PSOPs")
        result = []
        for row in psops:
            psop = _decode_psop(row[0])
            result.append(WorkflowSearchResult(
                workflow_id=psop.id,
                workflow_type="psop",
                name=psop.name,
                description=psop.description,
                tags=psop.tags,
                created_at=psop.created_at,
                user_intent=psop.user_intent,
                related_preflow=psop.related_preflow,
                tasks_summary=build_tasks_summary(psop),
                binding=generation_binding(psop),
            ))
        logger.debug(f"[DB] Listed {len(result)} PSOP(s)")
        return result
    finally:
        close_resource(conn)


def get_psop_by_id(psop_id):
    query_sql = "SELECT psop_content FROM psop WHERE id = %s"
    conn = require_connection(create_connection())
    try:
        results, error = execute_query(conn, query_sql, (psop_id,))
        if error:
            raise_storage_error(error, "Failed to load PSOP")
        if len(results) != 0:
            logger.debug(f"[DB] PSOP loaded (id={psop_id})")
            return _decode_psop(results[0][0])
        else:
            logger.warning(f"[DB] PSOP not found (id={psop_id})")
            return None
    finally:
        close_resource(conn)


def _decode_psop(content):
    try:
        return PSOP.model_validate(json.loads(content))
    except (ValueError, TypeError) as exc:
        raise StorageCorruptionError("Stored PSOP is invalid") from exc

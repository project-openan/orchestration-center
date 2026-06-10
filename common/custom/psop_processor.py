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

from typing import Optional

from loguru import logger

from database.utils.db_connection import create_connection
from database.utils.query_execution import execute_query
from orchestrate.core.model.psop import PSOP
from orchestrate.core.workflow_search_result import WorkflowSearchResult


def custom_save_psop(psop):
    save_sql = """
               INSERT INTO psop (id, name, description, psop_content)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                   name = EXCLUDED.name,
                   description = EXCLUDED.description,
                   psop_content = EXCLUDED.psop_content
               """
    conn = create_connection()
    if conn is None:
        raise RuntimeError("Unable to connect to database")
    try:
        _, error = execute_query(conn, save_sql, (psop.id, psop.name, psop.description, psop.model_dump_json()))
        if error:
            logger.error(f"[DB] Failed to save PSOP '{psop.name}' (id={psop.id}): {error}")
            raise RuntimeError(f"Failed to save PSOP: {error}")
        logger.info(f"[DB] PSOP saved: '{psop.name}' (id={psop.id})")
        return psop.id
    finally:
        conn.close()


def custom_delete_psop(workflow_id):
    delete_sql = "DELETE FROM psop WHERE id = %s"
    conn = create_connection()
    if conn is None:
        return False
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
            cur.close()
    except Exception as e:
        logger.error(f"[DB] Failed to delete PSOP (id={workflow_id}): {e}")
        return False
    finally:
        conn.close()


def build_tasks_summary(psop: PSOP) -> Optional[str]:
    task_descriptions = []
    for step in psop.steps[:8]:
        for task in step.subtasks[:3]:
            desc = (task.description or "").strip()
            if desc:
                task_descriptions.append(f"[{step.name}] {desc}")
    if not task_descriptions:
        return None
    return "; ".join(task_descriptions[:12])


def get_all_psops():
    query_sql = "SELECT psop_content FROM psop"
    conn = create_connection()
    if conn is None:
        return []
    try:
        psops, error = execute_query(conn, query_sql)
        if error:
            logger.error(f"[DB] Failed to list PSOPs: {error}")
            return []
        result = []
        for row in psops:
            psop = PSOP.model_validate(json.loads(row[0]))
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
            ))
        logger.debug(f"[DB] Listed {len(result)} PSOP(s)")
        return result
    finally:
        conn.close()


def get_psop_by_id(psop_id):
    query_sql = "SELECT psop_content FROM psop WHERE id = %s"
    conn = create_connection()
    if conn is None:
        return None
    try:
        results, error = execute_query(conn, query_sql, (psop_id,))
        if error:
            logger.error(f"[DB] Failed to load PSOP (id={psop_id}): {error}")
            return None
        if len(results) != 0:
            logger.debug(f"[DB] PSOP loaded (id={psop_id})")
            return PSOP.model_validate(json.loads(results[0][0]))
        else:
            logger.warning(f"[DB] PSOP not found (id={psop_id})")
            return None
    finally:
        conn.close()

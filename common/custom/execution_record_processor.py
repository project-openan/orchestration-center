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
from orchestrate.core.model.execution_record import ExecutionRecord


def db_save_execution_record(record: ExecutionRecord) -> str:
    save_sql = """
               INSERT INTO execution_records
                   (execution_id, psop_id, psop_name, started_at, completed_at, status, step_count, record_content)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               """
    conn = create_connection()
    if conn is None:
        raise RuntimeError("Unable to connect to database")
    try:
        _, error = execute_query(conn, save_sql, (
            record.execution_id,
            record.psop_id,
            record.psop_name,
            record.started_at,
            record.completed_at,
            record.status,
            len(record.execution_history),
            record.model_dump_json(),
        ))
        if error:
            logger.error(f"[DB] Failed to save execution record (id={record.execution_id}): {error}")
            raise RuntimeError(f"Failed to save execution record: {error}")
        logger.info(f"[DB] Execution record saved (id={record.execution_id}, psop='{record.psop_name}', status={record.status})")
        return record.execution_id
    finally:
        conn.close()


def db_list_execution_records():
    query_sql = """
                SELECT execution_id, psop_id, psop_name, started_at, completed_at,
                       status, step_count, record_content
                FROM execution_records ORDER BY started_at DESC
                """
    conn = create_connection()
    if conn is None:
        return []
    try:
        rows, error = execute_query(conn, query_sql)
        if error:
            logger.error(f"[DB] Failed to list execution records: {error}")
            return []
        result = []
        for row in rows:
            summary = {
                "execution_id": row[0],
                "psop_id": row[1],
                "psop_name": row[2],
                "started_at": row[3].isoformat() if hasattr(row[3], 'isoformat') else row[3],
                "completed_at": row[4].isoformat() if hasattr(row[4], 'isoformat') else row[4],
                "status": row[5],
                "step_count": row[6],
                "error": None,
            }
            try:
                content = json.loads(row[7]) if row[7] else {}
                summary["error"] = content.get("error")
            except Exception:
                logger.warning(f"[DB] Failed to parse execution record content for {row[0]}")
            result.append(summary)
        logger.debug(f"[DB] Listed {len(result)} execution record(s)")
        return result
    finally:
        conn.close()


def db_get_execution_record(execution_id: str):
    query_sql = "SELECT record_content FROM execution_records WHERE execution_id = %s"
    conn = create_connection()
    if conn is None:
        return None
    try:
        results, error = execute_query(conn, query_sql, (execution_id,))
        if error:
            logger.error(f"[DB] Failed to load execution record (id={execution_id}): {error}")
            return None
        if results and len(results) > 0:
            logger.debug(f"[DB] Execution record loaded (id={execution_id})")
            return ExecutionRecord.model_validate(json.loads(results[0][0]))
        logger.warning(f"[DB] Execution record not found (id={execution_id})")
        return None
    finally:
        conn.close()


def db_delete_execution_record(execution_id: str) -> bool:
    delete_sql = "DELETE FROM execution_records WHERE execution_id = %s"
    conn = create_connection()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(delete_sql, (execution_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"[DB] Execution record deleted (id={execution_id})")
            else:
                logger.warning(f"[DB] Execution record not found for deletion (id={execution_id})")
            return deleted
        finally:
            cur.close()
    except Exception as e:
        logger.error(f"[DB] Failed to delete execution record (id={execution_id}): {e}")
        return False
    finally:
        conn.close()

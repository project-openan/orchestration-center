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
from datetime import datetime

from loguru import logger

from database.utils.db_connection import create_connection
from database.utils.query_execution import execute_query
from database.utils.sql_dialect import upsert_sql, timestamp_parameter, timestamp_iso
from database.utils.storage_errors import require_connection, raise_storage_error, close_resource
from orchestrate.persistence.errors import StorageCorruptionError
from orchestrate.core.model.execution_record import ExecutionRecord


def db_save_execution_record(record: ExecutionRecord) -> str:
    save_sql = upsert_sql("execution_records", "execution_id", (
        "execution_id", "psop_id", "psop_name", "started_at", "completed_at",
        "status", "step_count", "record_content",
    ))
    conn = require_connection(create_connection())
    try:
        _, error = execute_query(conn, save_sql, (
            record.execution_id,
            record.psop_id,
            record.psop_name,
            timestamp_parameter(record.started_at),
            timestamp_parameter(record.completed_at),
            record.status,
            len(record.execution_history),
            record.model_dump_json(),
        ))
        if error:
            raise_storage_error(error, "Failed to save execution record")
        logger.info(f"[DB] Execution record saved (id={record.execution_id}, psop='{record.psop_name}', status={record.status})")
        return record.execution_id
    finally:
        close_resource(conn)


def db_list_execution_records():
    query_sql = """
                SELECT execution_id, psop_id, psop_name, started_at, completed_at,
                       status, step_count, record_content
                FROM execution_records ORDER BY started_at DESC
                """
    conn = require_connection(create_connection())
    try:
        rows, error = execute_query(conn, query_sql)
        if error:
            raise_storage_error(error, "Failed to list execution records")
        result = []
        for row in rows:
            summary = {
                "execution_id": row[0],
                "psop_id": row[1],
                "psop_name": row[2],
                "started_at": timestamp_iso(row[3]),
                "completed_at": timestamp_iso(row[4]),
                "status": row[5],
                "step_count": row[6],
                "error": None,
            }
            # Legacy rows may omit the nullable snapshot; their scalar summary
            # is still usable. A present but invalid snapshot is corruption.
            if row[7] is not None:
                try:
                    content = json.loads(row[7])
                    summary["error"] = content.get("error")
                    # The immutable snapshot retains the original offset even
                    # for legacy PostgreSQL rows written in a session timezone.
                    # Prefer it over the ambiguous timestamp scalar when present.
                    for field in ("started_at", "completed_at"):
                        if field in content:
                            value = content[field]
                            summary[field] = timestamp_iso(datetime.fromisoformat(value)) if value is not None else None
                except (ValueError, TypeError, AttributeError) as exc:
                    raise StorageCorruptionError("Stored execution record is invalid") from exc
            result.append(summary)
        logger.debug(f"[DB] Listed {len(result)} execution record(s)")
        return result
    finally:
        close_resource(conn)


def db_get_execution_record(execution_id: str):
    query_sql = "SELECT record_content FROM execution_records WHERE execution_id = %s"
    conn = require_connection(create_connection())
    try:
        results, error = execute_query(conn, query_sql, (execution_id,))
        if error:
            raise_storage_error(error, "Failed to load execution record")
        if results and len(results) > 0:
            logger.debug(f"[DB] Execution record loaded (id={execution_id})")
            try:
                return ExecutionRecord.model_validate(json.loads(results[0][0]))
            except (ValueError, TypeError) as exc:
                raise StorageCorruptionError("Stored execution record is invalid") from exc
        logger.warning(f"[DB] Execution record not found (id={execution_id})")
        return None
    finally:
        close_resource(conn)


def db_delete_execution_record(execution_id: str) -> bool:
    delete_sql = "DELETE FROM execution_records WHERE execution_id = %s"
    conn = require_connection(create_connection())
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
            close_resource(cur)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logger.warning("[DB] Rollback failed while deleting execution record")
        raise_storage_error(e, "Failed to delete execution record")
    finally:
        close_resource(conn)

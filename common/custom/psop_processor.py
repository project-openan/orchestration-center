# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

from database.utils.db_connection import create_connection
from database.utils.query_execution import execute_query
from orchestrate.core.model.psop import PSOP
from orchestrate.core.workflow_search_result import WorkflowSearchResult


def custom_save_psop(psop):
    save_sql = """
               INSERT INTO psop (id, name, description, psop_content)
               VALUES (%s, %s, %s, %s)
               """
    conn = create_connection()
    execute_query(conn, save_sql, (psop.id, psop.name, psop.description, psop.model_dump_json()))
    conn.close()
    return psop.id


def custom_delete_psop(workflow_id):
    delete_sql = "DELETE FROM psop WHERE id = %s"
    conn = create_connection()
    result, error = execute_query(conn, delete_sql, (workflow_id,))
    conn.close()
    return True if error is None else False


def get_all_psops():
    query_sql = "SELECT psop_content FROM psop"
    conn = create_connection()
    psops, _ = execute_query(conn, query_sql)
    conn.close()
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
        ))
    return result


def get_psop_by_id(psop_id):
    quert_sql = "SELECT psop_content FROM psop WHERE id = %s"
    conn = create_connection()
    results, _ = execute_query(conn, quert_sql, (psop_id,))
    conn.close()
    if len(results) != 0:
        return PSOP.model_validate(json.loads(results[0][0]))
    else:
        return None

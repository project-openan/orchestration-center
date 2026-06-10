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

from loguru import logger


def execute_query(conn, query, params=None):
    if conn is None:
        logger.error("Database connection is None")
        return None, RuntimeError("No database connection")
    query = query.strip()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if query.upper().strip().startswith("SELECT"):
            results = cur.fetchall()
            return results, None
        else:
            conn.commit()
            return None, None
    except Exception as error:
        logger.error(f"DB error: {error}")
        return None, error
    finally:
        cur.close()
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
import os.path

import psycopg2
from loguru import logger
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def read_db_config(file_name):
    current_dir = os.path.abspath(__file__)
    grand_parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    dir_path = os.path.join(grand_parent_dir, 'etc', 'conf')
    file_path = os.path.join(dir_path, file_name)
    with open(file_path, "r", encoding='utf-8') as f:
        return json.load(f)


conn_info = read_db_config("db_config.json")


def create_database_if_not_exists():
    default_conn_info = {**conn_info,  "database": "postgres"}
    try:
        conn = psycopg2.connect(**default_conn_info)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if the database exists
        database_name = conn_info.get('database', "orchestration-center")
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'")
        exists = cursor.fetchone()

        if not exists:
            # Create the database
            cursor.execute(f'CREATE DATABASE {database_name}')
            print(f"Database {database_name} created successfully")

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
        conn = psycopg2.connect(**conn_info)
        return conn
    except Exception as e:
        logger.error(f"Unable to connect to database: {e}")

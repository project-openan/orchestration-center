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

from common.custom.default_handle import BaseHandler
from common.custom.psop_processor import custom_save_psop, custom_delete_psop, get_all_psops, get_psop_by_id
from common.custom.execution_record_processor import (
    db_save_execution_record,
    db_list_execution_records,
    db_get_execution_record,
    db_delete_execution_record,
)
from loguru import logger


class CustomSavePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomSavePsopHandler invoked")
        return custom_save_psop(*args, **kwargs)


class CustomDeletePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomDeletePsopHandler invoked")
        return custom_delete_psop(*args, **kwargs)


class CustomGetAllPsopsHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomGetAllPsopsHandler invoked")
        return get_all_psops(*args, **kwargs)


class CustomGetPsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomGetPsopHandler invoked")
        return get_psop_by_id(*args, **kwargs)


class CustomSaveExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomSaveExecutionRecordHandler invoked")
        return db_save_execution_record(*args, **kwargs)


class CustomListExecutionRecordsHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomListExecutionRecordsHandler invoked")
        return db_list_execution_records(*args, **kwargs)


class CustomGetExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomGetExecutionRecordHandler invoked")
        return db_get_execution_record(*args, **kwargs)


class CustomDeleteExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        logger.debug("[DB] CustomDeleteExecutionRecordHandler invoked")
        return db_delete_execution_record(*args, **kwargs)

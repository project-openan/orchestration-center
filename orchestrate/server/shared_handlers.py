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

import anyio
from common.custom.default_handle import HandlerRegistry
from common.custom.interface_type import InterfaceType
from common.util.config_util import get_conf
from orchestrate.core.retrieval import WorkflowRetrieval
from orchestrate.workflow_storage_instance import get_workflow_storage


def get_semaphore(config_key: str, default: int) -> anyio.Semaphore:
    return anyio.Semaphore(int(get_conf().get(config_key, default)))


def try_acquire(sem: anyio.Semaphore):
    try:
        sem.acquire_nowait()
        return True
    except anyio.WouldBlock:
        return False


class SharedHandlers:
    _save_handle = None
    _delete_handle = None
    _retrieval = None

    @classmethod
    def save_psop(cls):
        if cls._save_handle is None:
            cls._save_handle = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        return cls._save_handle

    @classmethod
    def delete_psop(cls):
        if cls._delete_handle is None:
            cls._delete_handle = HandlerRegistry.get_handler(InterfaceType.DELETE_PSOP)
        return cls._delete_handle

    @classmethod
    def retrieval(cls):
        if cls._retrieval is None:
            cls._retrieval = WorkflowRetrieval(get_workflow_storage())
        return cls._retrieval

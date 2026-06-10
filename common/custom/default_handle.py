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

from abc import ABC, abstractmethod
from typing import Dict, Type

from loguru import logger

from common.custom.interface_type import InterfaceType
from common.util.config_util import get_conf
from orchestrate.core.workflow_search_result import WorkflowSearchResult
from orchestrate.workflow_storage_instance import get_workflow_storage


class BaseHandler(ABC):
    """Abstract base class requiring subclasses to implement the handle method."""

    @abstractmethod
    def handle(self, *args, **kwargs):
        """Concrete business logic is implemented by subclasses."""
        pass


# ==================== Default implementations ====================
class SavePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().save_psop(*args)


class GetAllPsopsHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        results = []
        storage = get_workflow_storage()
        for wf_id in storage.list_psops():
            psop = storage.load_psop(wf_id)
            if psop:
                results.append(WorkflowSearchResult(
                    workflow_id=psop.id,
                    workflow_type="psop",
                    name=psop.name,
                    description=psop.description,
                    tags=psop.tags,
                    created_at=psop.created_at,
                    user_intent=psop.user_intent,
                    related_preflow=psop.related_preflow,
                ))
        return results


class GetPsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        storage = get_workflow_storage()
        return storage.load_psop(*args)


class DeletePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().delete_psop(*args)


# ==================== Execution Record default handlers ====================
class SaveExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().save_execution_record(*args)


class ListExecutionRecordsHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().list_execution_records()


class GetExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().load_execution_record(*args)


class DeleteExecutionRecordHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_workflow_storage().delete_execution_record(*args)


# ==================== Registry ====================
class HandlerRegistry:
    _registry: Dict[str, Type[BaseHandler]] = {}

    @classmethod
    def register(cls, interface_type: InterfaceType, handler_class: Type[BaseHandler]) -> None:
        """
        Register a user-customized implementation class.
        :param interface_type: Interface type identifier, e.g., "decrypt", "audit", "authenticate", "insert", "query"
        :param handler_class: Custom class inheriting from BaseHandler
        """
        if not issubclass(handler_class, BaseHandler):
            raise TypeError("handler_class must be a subclass of BaseHandler")
        cls._registry[interface_type.value] = handler_class

    @classmethod
    def get_handler(cls, interface_type: InterfaceType) -> BaseHandler:
        persistence_mode = get_conf().get("persistence_mode", "file")
        if persistence_mode.lower() != "file":
            if interface_type.value in cls._registry:
                logger.debug(f"[Registry] Dispatching '{interface_type.value}' → DB handler (mode={persistence_mode})")
                return cls._registry[interface_type.value]()
            else:
                raise ValueError(
                    f"No custom handler registered for '{interface_type.value}' "
                    f"but persistence_mode={persistence_mode}. "
                    "Register a handler via HandlerRegistry.register() first."
                )
        logger.debug(f"[Registry] Dispatching '{interface_type.value}' → file handler (mode={persistence_mode})")
        default_map = {
            "save_psop": SavePsopHandler,
            "get_all_psop": GetAllPsopsHandler,
            "get_psop_by_id": GetPsopHandler,
            "delete_psop": DeletePsopHandler,
            "save_execution_record": SaveExecutionRecordHandler,
            "list_execution_records": ListExecutionRecordsHandler,
            "get_execution_record": GetExecutionRecordHandler,
            "delete_execution_record": DeleteExecutionRecordHandler,
        }
        handler_class = default_map.get(interface_type.value)
        if handler_class is None:
            raise ValueError(f"Unknown interface type: {interface_type}")
        return handler_class()


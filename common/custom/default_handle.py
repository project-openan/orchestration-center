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

from abc import ABC, abstractmethod
from typing import Dict, Type

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
                ))
        return results


class GetPsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        storage = get_workflow_storage()
        return storage.load_psop(*args)


class DeletePsopHandler(BaseHandler):
    async def handle(self, *args, **kwargs):
        return get_workflow_storage().delete_psop(*args)


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
        """
        Get a handler instance based on the interface type.
        :param interface_type: Interface type identifier
        :return: BaseHandler instance (user-customized or default)
        """
        persistence_mode = get_conf().get("persistence_mode", "file")
        if persistence_mode.lower() != "file" and interface_type.value in cls._registry:
            # If a user-registered class exists, instantiate and return it
            return cls._registry[interface_type.value]()
        else:
            # Otherwise, return the corresponding default implementation
            default_map = {
                "save_psop": SavePsopHandler,
                "get_all_psop": GetAllPsopsHandler,
                "get_psop_by_id": GetPsopHandler,
                "delete_psop": DeletePsopHandler,
            }
            handler_class = default_map.get(interface_type.value)
            if handler_class is None:
                raise ValueError(f"Unknown interface type: {interface_type}")
            return handler_class()


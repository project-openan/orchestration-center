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

from common.custom.custom_handle import (
    CustomSavePsopHandler,
    CustomDeletePsopHandler,
    CustomGetAllPsopsPsopHandler,
    CustomGetPsopPsopHandler,
)
from common.custom.default_handle import HandlerRegistry
from common.custom.interface_type import InterfaceType

HandlerRegistry.register(InterfaceType.SAVE_PSOP, CustomSavePsopHandler)
HandlerRegistry.register(InterfaceType.DELETE_PSOP, CustomDeletePsopHandler)
HandlerRegistry.register(InterfaceType.GET_ALL_PSOP, CustomGetAllPsopsPsopHandler)
HandlerRegistry.register(InterfaceType.GET_PSOP_BY_ID, CustomGetPsopPsopHandler)
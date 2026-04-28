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

from common.custom.default_handle import BaseHandler
from common.custom.psop_processor import custom_save_psop, custom_delete_psop, get_all_psops, get_psop_by_id


class CustomSavePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return custom_save_psop(*args)


class CustomDeletePsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return custom_delete_psop(*args)


class CustomGetAllPsopsPsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
        return get_all_psops()


class CustomGetPsopPsopHandler(BaseHandler):
    def handle(self, *args, **kwargs):
       return get_psop_by_id(*args)

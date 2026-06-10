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

from enum import Enum
from typing import Any, Optional, Dict


class AuthFailureReason(Enum):
    INVALID_CREDENTIALS = "Invalid credentials"

class AuthenticationError(Exception):
    def __init__(self, reason:AuthFailureReason, detail:str = None):
        self.reason = reason
        self.detail = detail
        super().__init__(self.detail)


class Principal:
    def __init__(self, client_ip:str):
        self.client_ip = client_ip


def authenticate(client_ip:str, request:Any, context:Optional[Dict[str, Any]]) -> Principal:
    try:
        return Principal(client_ip)
    except Exception as ex:
        raise AuthenticationError(AuthFailureReason.INVALID_CREDENTIALS, "Invalid credentials") from ex
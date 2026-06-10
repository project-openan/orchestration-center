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

import uuid
import hashlib
import base64
import random
import string
import time
from datetime import datetime
from typing import Dict, Callable


def _build_aoc_signed_headers(params: Dict[str, str]) -> Dict[str, str]:
    app_key = params['app_key']
    app_secret = params['app_secret']

    message_id = str(uuid.uuid4()).replace('-', '')
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d%H%M%S') + f"{now.microsecond // 1000:03d}"

    raw_sign = f"{message_id}{app_secret}{timestamp}"
    md5_secret = base64.b64encode(hashlib.md5(raw_sign.encode('utf-8')).digest()).decode('utf-8')

    hex_time = format(int(time.time()), 'x')
    scenario_id = hex_time + ''.join(random.choices(string.hexdigits.lower(), k=24))
    span_id = ''.join(random.choices(string.hexdigits.lower(), k=16))

    return {
        'Content-Type': 'application/json',
        'Authorization': params.get('authorization', ''),
        'x-sg-app-key': app_key,
        'x-sg-test': params.get('test_flag', '1'),
        'x-sg-message-id': message_id,
        'x-sg-timestamp': timestamp,
        'x-sg-md5-secret': md5_secret,
        'x-sg-scenario-code': params.get('scenario_code', 'B99999999999'),
        'x-sg-scenario-version': params.get('scenario_version', 'V1'),
        'x-sg-ability-code': params.get('ability_code', 'A999999999'),
        'x-sg-api-code': params.get('api_code', ""),
        'x-sg-api-version': params.get('api_version', '1.0'),
        'x-sg-scenario-id': scenario_id,
        'x-sg-spanid': span_id,
    }


AUTH_STRATEGIES: Dict[str, Callable] = {
    "aoc_signed": _build_aoc_signed_headers,
}

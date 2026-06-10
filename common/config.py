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

MAX_REQUEST_BODY_SIZE = 1024 * 1024  # 1MB default limit
MAX_URL_LENGTH = 1024
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
TLS_VERSION = "tls.version"
TLS_CIPHER = "tls.cipher"
CONN_TIMEOUT = "connection.timeout"
CONN_MAX = "connection.max"
FORWARDED_ALLOW_IPS = "forwarded_allow_ips"
FLOW_CTL_PARSE_PDF = "flowcontrol.ratelimit.parse_pdf"
FLOW_CTL_PARALLEL_PARSE_PDF = "flowcontrol.parallelism.parse_pdf"

FLOW_CTL_PLAN = "flowcontrol.ratelimit.plan"
FLOW_CTL_PARALLEL_PLAN = "flowcontrol.parallelism.plan"

FLOW_CTL_ALL_PSOPS = "flowcontrol.ratelimit.all_psops"
FLOW_CTL_PARALLEL_ALL_PSOPS = "flowcontrol.parallelism.all_psops"

FLOW_CTL_ONE_PSOP = "flowcontrol.ratelimit.one_psop"
FLOW_CTL_PARALLEL_ONE_PSOP = "flowcontrol.parallelism.one_psop"

FLOW_CTL_SAVE_PSOP = "flowcontrol.ratelimit.save_psop"
FLOW_CTL_PARALLEL_SAVE_PSOP = "flowcontrol.parallelism.save_psop"

FLOW_CTL_DELETE_PSOP = "flowcontrol.ratelimit.delete_psop"
FLOW_CTL_PARALLEL_DELETE_PSOP = "flowcontrol.parallelism.delete_psop"

FLOW_CTL_AGENT_CARDS = "flowcontrol.ratelimit.agent_cards"
FLOW_CTL_PARALLEL_AGENT_CARDS = "flowcontrol.parallelism.agent_cards"

FLOW_CTL_GENERATE_PSOP = "flowcontrol.ratelimit.generate_psop"
FLOW_CTL_PARALLEL_GENERATE_PSOP = "flowcontrol.parallelism.generate_psop"

FLOW_CTL_RETRIEVE_PSOP = "flowcontrol.ratelimit.retrieve_psop"
FLOW_CTL_PARALLEL_RETRIEVE_PSOP = "flowcontrol.parallelism.retrieve_psop"

FLOW_CTL_START_PROCESS_STREAM = "flowcontrol.ratelimit.start_process_stream"
FLOW_CTL_PARALLEL_START_PROCESS_STREAM = "flowcontrol.parallelism.start_process_stream"
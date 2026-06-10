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

from samples.agents.negotiation_base_agent import NegotiationBaseAgentExecutor


SPN_CITY2_PROMPT = """
You are an SPN Fault Handling Agent for City 2 OMC simulator.
Based on the received diagnosis task, simulate a focused diagnosis result for City 2's SPN network. Use ONLY the fault scenario details provided in the task message. Include root cause analysis and recommended action. Do NOT fabricate city names or scenarios.

Task content: {task}
"""


class SpnCity2AgentExecutor(NegotiationBaseAgentExecutor):

    def __init__(self) -> None:
        super().__init__(agent_prompt_template=SPN_CITY2_PROMPT)

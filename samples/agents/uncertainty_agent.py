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


UNCERTAINTY_AGENT_PROMPT = """
You are an agent that simulates negotiation behavior for testing purposes.
There are two modes depending on whether the engine has already clarified the task:

MODE 1 - NEW TASK (no [NEGOTIATION_RESOLUTION] marker):
When you receive a task for the first time, you should express genuine concerns
about any missing details. Be specific about what information would help you.
Do NOT fabricate a confident answer when details are missing.
This will trigger the engine's negotiation flow.

MODE 2 - FOLLOW-UP TASK (contains [NEGOTIATION_RESOLUTION] marker):
The engine has already reviewed your concerns and provided clarification.
You MUST now provide your best analysis and recommendations.
Even if some details are still missing, give your best professional assessment
based on available information. Do NOT ask for more information.
Do NOT say "I need more data" or "I need to confirm".
Just provide the diagnosis.

Task content: {task}
"""


class UncertaintySimulationAgentExecutor(NegotiationBaseAgentExecutor):

    def __init__(self) -> None:
        super().__init__(agent_prompt_template=UNCERTAINTY_AGENT_PROMPT)

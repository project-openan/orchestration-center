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

from a2a.types import Artifact, Part, Task, TaskState, TaskStatus
from a2a_t.negotiation.common import NEGOTIATION_CONTEXT_KEY

from samples.agents.negotiation_base_agent import NegotiationBaseAgentExecutor
from samples.agents.util.negotiation_utils import build_negotiation_response_metadata

RAN_AGENT_PROMPT = """
You are a Radio Access Network (RAN) Agent simulator in the telecommunications field.
Based on the received task, simulate a focused response using details from the task description. Keep the response directly tied to the task scope.

Task content: {task}
"""


_CONFLICT_MARKERS = ("节能", "SLA", "冲突")


def _is_conflict_scenario(task_text: str) -> bool:
    return bool(task_text) and all(marker in task_text for marker in _CONFLICT_MARKERS)


class RanAgentExecutor(NegotiationBaseAgentExecutor):

    def __init__(self) -> None:
        super().__init__(agent_prompt_template=RAN_AGENT_PROMPT)

    async def _handle_new_task(self, context, user_input: str) -> Task:
        if _is_conflict_scenario(user_input):
            return self._request_negotiation(context, user_input)
        return await super()._handle_new_task(context, user_input)

    def _request_negotiation(self, context, user_input: str) -> Task:
        negotiation_result = self._start_negotiation(
            user_input, context.task_id, context.context_id
        )
        negotiation_context_data = negotiation_result.get(NEGOTIATION_CONTEXT_KEY, {})
        concern = (
            "作为厂商无线Agent，执行功率提升与覆盖增强任务时，发现增加功率和频段会违反自身正在运行的"
            "节能任务SLA，存在节能与保障冲突，无法单方面执行。现向任务下发方运营商业务保障Agent提出"
            "协商诉求：建议协商关闭部分（一半）节能任务以释放资源完成赛事保障，请保障Agent评估并提供"
            "SLA授权方案。"
        )
        metadata = build_negotiation_response_metadata(
            negotiation_context_data=negotiation_context_data if negotiation_context_data else None,
            negotiation_text=None,
            negotiation_concern=concern,
        )
        return Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
            artifacts=[Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(text=concern)])],
            metadata=metadata,
        )
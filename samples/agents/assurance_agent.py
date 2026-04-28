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

import asyncio
import uuid
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Task, TaskStatus, TaskState, Artifact, Part,
)
from loguru import logger

from common.llm import get_llm_instance


class AssuranceAgentExecutor(AgentExecutor):

    def __init__(self) -> None:
        self.llm = get_llm_instance()

    async def execute(
            self,
            context: RequestContext,
            event_queue: EventQueue,
    ) -> None:
        prompt = context.get_user_input()
        response = await asyncio.to_thread(self.answer_query, prompt)
        task = Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[
                Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(text=response)])
            ]
        )
        await event_queue.enqueue_event(task)

    def answer_query(self, user_message: str):
        prompt = f"""
        你是保障策略智能体（Assurance Agent），负责生成并下发保障策略及其恢复策略。
        请根据收到的用户任务，模拟一个简短的成功响应。

        任务内容: {user_message}
        直接输出中文响应，不用输出其他内容。
        """
        _, res = self.llm.ask_llm(prompt)
        logger.info(res)
        return res

    async def cancel(
            self,
            context: RequestContext,
            event_queue: EventQueue,
    ) -> None:
        pass

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

import asyncio
import uuid
from typing import Dict, Any
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Task, TaskStatus, TaskState, Artifact, Part
from loguru import logger

from a2a_t.server import A2ATServer
from a2a_t.negotiation.common.enums import NegotiationType
from a2a_t.negotiation.common.models import StartNegotiationInput, NegotiationContext

from common.a2at_config import get_a2at_env_path
from common.llm import get_llm_instance
from common.negotiation_utils import (
    NEGOTIATION_CONTEXT_KEY,
    NEGOTIATION_TEXT_KEY,
    NEGOTIATION_REQUEST_MARKER,
    build_negotiation_metadata,
    log_negotiation_context,
    is_uncertain_response,
    is_follow_up_task,
    extract_original_task_from_follow_up,
    extract_continued_context_from_follow_up,
    cleanup_negotiation_resolution_marker,
)


class NegotiationBaseAgentExecutor(AgentExecutor):
    def __init__(self, agent_prompt_template: str) -> None:
        self.llm = get_llm_instance()
        env_path = get_a2at_env_path()
        self.a2at_server = A2ATServer(env_path=env_path)
        self.prompt_template = agent_prompt_template
        logger.info(f"[{self.__class__.__name__}] Initialized with A2ATServer, env_path={env_path}")

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_input = context.get_user_input()
        task_id = context.task_id or "N/A"
        ctx_id = context.context_id or "N/A"
        logger.info(f"[{self.__class__.__name__}] execute: task_id={task_id}, context_id={ctx_id}")

        task_t_uri = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"
        try:
            if hasattr(context, 'message') and context.message:
                msg = context.message
                if msg.metadata and task_t_uri in msg.metadata:
                    task_t_text = msg.metadata[task_t_uri]
                    if isinstance(task_t_text, str) and len(task_t_text) > len(user_input or ''):
                        logger.info(f"[{self.__class__.__name__}] Using TASK-T prompt from message metadata")
                        user_input = task_t_text
        except Exception as e:
            logger.debug(f"[{self.__class__.__name__}] Could not read TASK-T metadata: {e}")

        if is_follow_up_task(user_input):
            task = await self._handle_follow_up_task(context, user_input)
        else:
            task = await self._handle_new_task(context, user_input)

        await event_queue.enqueue_event(task)

    async def _handle_new_task(self, context: RequestContext, user_input: str) -> Task:
        negotiation_result = self._start_negotiation(user_input, context.task_id, context.context_id)

        negotiation_context_data = negotiation_result.get(NEGOTIATION_CONTEXT_KEY, {})
        negotiation_text = negotiation_result.get(NEGOTIATION_TEXT_KEY, "")
        if negotiation_context_data:
            try:
                negotiation_ctx = NegotiationContext.from_context(negotiation_context_data)
                log_negotiation_context(negotiation_ctx, f"[{self.__class__.__name__}]")
            except Exception as e:
                logger.warning(f"Failed to parse negotiation context: {e}")

        response = await asyncio.to_thread(self._execute_task, user_input, context.task_id, context.context_id)

        uncertain = await asyncio.to_thread(is_uncertain_response, response, self.llm)
        if uncertain:
            logger.info(f"[{self.__class__.__name__}] Response indicates uncertainty, requesting negotiation")
            metadata: Dict[str, Any] = {}
            if negotiation_context_data:
                metadata["negotiationContext"] = negotiation_context_data
            if negotiation_text:
                metadata["negotiationText"] = negotiation_text
            metadata["negotiationConcern"] = response
            return Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED),
                artifacts=[
                    Artifact(
                        artifact_id=str(uuid.uuid4()),
                        parts=[Part(text=f"{NEGOTIATION_REQUEST_MARKER} {self.__class__.__name__} needs more information to complete this task.\n{response}")]
                    )
                ],
                metadata=metadata
            )

        return self._build_task_response(
            context=context,
            response=response,
            negotiation_context=negotiation_context_data,
        )

    async def _handle_follow_up_task(self, context: RequestContext, user_input: str) -> Task:
        logger.info(f"[{self.__class__.__name__}] Detected follow-up task with negotiation resolution")
        cleaned_input = cleanup_negotiation_resolution_marker(user_input)
        original_task = extract_original_task_from_follow_up(user_input)

        continued_context = extract_continued_context_from_follow_up(user_input)
        if continued_context:
            try:
                continued_ctx = NegotiationContext.from_context(continued_context)
                log_negotiation_context(continued_ctx, f"[{self.__class__.__name__}] continued negotiation")
                if continued_ctx.status.value == "agreed":
                    logger.info(f"[{self.__class__.__name__}] Negotiation agreed at round {continued_ctx.round}, executing")
                negotiation_context_data = continued_context
            except Exception as e:
                logger.warning(f"Failed to parse continued negotiation context: {e}")
                _ = self._start_negotiation(cleaned_input or user_input, context.task_id, context.context_id)
                negotiation_context_data = {}
        else:
            _ = self._start_negotiation(cleaned_input or user_input, context.task_id, context.context_id)
            negotiation_context_data = {}

        execute_input = cleaned_input if cleaned_input else user_input
        response = await asyncio.to_thread(self._execute_task, execute_input, context.task_id, context.context_id)

        return self._build_task_response(
            context=context,
            response=response,
            negotiation_context=negotiation_context_data,
        )

    def _start_negotiation(self, user_input: str, task_id: str = None, context_id: str = None) -> Dict[str, Any]:
        try:
            facts = {"agent": self.__class__.__name__}
            if task_id:
                facts["task_id"] = task_id
            if context_id:
                facts["context_id"] = context_id
            negotiation_result = self.a2at_server.start_negotiation(
                StartNegotiationInput(
                    type=NegotiationType.FULFILLMENT,
                    content_text=user_input,
                    facts=facts
                )
            )
            negotiation_text = negotiation_result.get(NEGOTIATION_TEXT_KEY)
            if negotiation_text:
                logger.info(f"[{self.__class__.__name__}] Started fulfillment negotiation: {negotiation_text[:100]}...")
            else:
                logger.info(f"[{self.__class__.__name__}] Started fulfillment negotiation (no text in result)")
            return negotiation_result
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Failed to start negotiation: {e}")
            return {}

    def _execute_task(self, user_input: str, task_id: str = None, context_id: str = None) -> str:
        prompt = self.prompt_template.format(task=user_input)
        ctx_lines = []
        if task_id:
            ctx_lines.append(f"Task ID: {task_id}")
        if context_id:
            ctx_lines.append(f"Context ID: {context_id}")
        if ctx_lines:
            prompt = "## Execution Context\n" + "\n".join(ctx_lines) + "\n\n" + prompt
        _, res = self.llm.ask_llm(prompt)
        logger.info(f"[{self.__class__.__name__}] Task: {user_input[:50]}..., Result: {res[:100]}...")
        return res

    def _build_task_response(
        self,
        context: RequestContext,
        response: str,
        negotiation_context: Dict[str, Any]
    ) -> Task:
        metadata: Dict[str, Any] = {}
        if negotiation_context:
            metadata["negotiationContext"] = negotiation_context

        return Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[
                Artifact(
                    artifact_id=str(uuid.uuid4()),
                    parts=[Part(text=response)]
                )
            ],
            metadata=metadata
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        logger.info(f"[{self.__class__.__name__}] Task cancelled: task_id={context.task_id}, context_id={context.context_id}")

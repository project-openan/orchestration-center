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

"""OrchestrationEngine -- thin A2A-T channel to the Workbench Agent.

The orchestration center:
1. Searches/loads the PSOP (for frontend graph preview via psop_update)
2. Sends the intent to the Workbench Agent via A2A-T
3. Streams back SDK events from TaskUpdate metadata to the frontend SSE

All workflow execution logic (ControlPoint, extension pre-positioning,
agent card loading) lives in the Workbench Agent.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

from a2a.types import Part
from loguru import logger
from workflow_engine import A2ATransport, MessageContent, WorkflowEngineClient

try:
    from a2a_t.llm.factory import LLMClientFactory as _LLMFactory
    from a2a_t.llm.providers.openai import OpenAIClient as _OpenAIClient
    _LLMFactory.register("deepseek", _OpenAIClient)
except Exception:
    pass


class OrchestrationEngine:
    """Thin orchestration channel -- PSOP preview + A2A-T dispatch + event forward."""

    def __init__(self, agent_cards, target_agent: str = None, lang: str = None):
        from common.util.config_util import get_conf

        self.lang = lang or "zh"
        self._agent_cards = agent_cards
        self._target_agent = target_agent or get_conf().get("workflow_host_agent_name", "Host Agent")

        self._ssl_verify = str(get_conf().get("client_verify_server", "false")).lower() == "true"

        cred_path = Path(__file__).resolve().parent.parent.parent / "samples" / "agent_credentials.json"
        self._cred_path = str(cred_path) if cred_path.is_file() else None

    def _find_target_card(self):
        if not self._target_agent:
            return None
        for card in self._agent_cards:
            name = getattr(card, "name", "") or ""
            if name == self._target_agent:
                return card
        return None

    def _get_engine_client(self) -> WorkflowEngineClient:
        target_card = self._find_target_card()
        if target_card is None:
            raise RuntimeError(f"Agent '{self._target_agent}' not found in registry")
        transport = A2ATransport(
            agent_cards=[target_card],
            credentials_config=self._cred_path,
            ssl_verify=self._ssl_verify,
        )
        return WorkflowEngineClient.owning(transport, max_negotiation_exchanges=3)

    async def events(self, intent: str) -> AsyncIterator[dict]:
        """Search PSOP for preview, dispatch to target agent, stream back events."""
        from orchestrate.server.shared_handlers import SharedHandlers

        yield {
            "type": "start",
            "data": {"workflow": intent[:80], "intent": intent, "phase": "searching", "target_agent": self._target_agent},
            "timestamp": time.time(),
        }

        logger.info(f"[Orchestration] Searching PSOP for intent: {intent[:80]}")
        retrieval = SharedHandlers.retrieval()
        results = await asyncio.to_thread(retrieval.retrieve_psop_by_intent_topn, intent, 3)

        psop_model = None
        if results:
            psop_id = results[0].workflow_id
            workflow_name = results[0].name or psop_id
            logger.info(f"[Orchestration] Found PSOP: {psop_id} ({workflow_name})")

            yield {
                "type": "start",
                "data": {"workflow": workflow_name, "workflow_id": psop_id, "phase": "loading"},
                "timestamp": time.time(),
            }

            psop_model = await asyncio.to_thread(retrieval.get_psop_by_id, psop_id)
            if psop_model:
                logger.info(f"[Orchestration] Loaded workflow: {psop_model.name} ({len(psop_model.steps)} steps)")
                yield {
                    "type": "psop_update",
                    "data": {"psop": psop_model.model_dump()},
                    "timestamp": time.time(),
                }
        else:
            logger.warning("[Orchestration] No matching PSOP found, dispatching raw intent")

        engine_client = self._get_engine_client()

        yield {
            "type": "start",
            "data": {
                "workflow": psop_model.name if psop_model else intent[:80],
                "intent": intent,
                "phase": "dispatching",
                "target_agent": self._target_agent,
            },
            "timestamp": time.time(),
        }

        logger.info(f"[Orchestration] Dispatching intent to {self._target_agent}: {intent[:80]}")

        dispatch_metadata = {}
        if psop_model:
            dispatch_metadata["__orch_psop_id__"] = psop_model.id
            dispatch_metadata["__orch_psop__"] = json.dumps(
                psop_model.model_dump(mode="json"),
                ensure_ascii=False,
            )
            logger.info(f"[Orchestration] Passing psop_id={psop_model.id} to target agent")

        try:
            content = MessageContent(
                parts=(Part(text=intent),),
                metadata=dispatch_metadata,
            )
            async for response in engine_client.stream_message(
                self._target_agent, content,
            ):
                sdk_event_json = response.metadata.get("__sdk_event__")
                if sdk_event_json:
                    try:
                        event = json.loads(sdk_event_json)
                        if event.get("type") == "task_status_changed" and psop_model:
                            for shaped in self._shape_psop_update(event, psop_model):
                                yield shaped
                        else:
                            yield event
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"[Orchestration] Failed to parse __sdk_event__: {e}")

        except Exception as e:
            logger.error(f"[Orchestration] Workflow execution failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"error": str(e)},
                "timestamp": time.time(),
            }
        finally:
            with suppress(Exception):
                await engine_client.close()

    def _shape_psop_update(self, event: dict, psop_model) -> list:
        """Inject psop_update before task_status_changed for live graph updates."""
        from orchestrate.core.model.psop import TaskStatus as PSOPTaskStatus
        d = event.get("data", {})
        step_name = d.get("step")
        subtask_index = d.get("subtask_index", 0)
        status_str = d.get("status", "pending")
        try:
            status = PSOPTaskStatus(status_str)
        except Exception:
            status = PSOPTaskStatus.PENDING
        for s in psop_model.steps:
            if s.name == step_name:
                if 0 <= subtask_index < len(s.subtasks):
                    s.subtasks[subtask_index].status = status
                break
        yield {"type": "psop_update", "data": {"psop": psop_model.model_dump()}, "timestamp": time.time()}
        yield event

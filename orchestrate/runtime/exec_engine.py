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
import atexit
import json
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.client.auth import AuthInterceptor
from a2a.client.auth import CredentialService
from a2a.helpers import new_text_message
from a2a.types import SendMessageRequest
from google.protobuf.json_format import MessageToJson, MessageToDict
from loguru import logger

try:
    from a2a_t.client import A2ATClient
    _A2AT_AVAILABLE = True
except ImportError:
    _A2AT_AVAILABLE = False
    A2ATClient = None

from common.llm import get_llm_instance
from common.auth import get_auth_manager
from common.auth.extension_interceptor import ExtensionInterceptor
from orchestrate.core.model.psop import PSOP, Step, StepType, Task, TaskStatus

class DynamicWorkflowEngine:
    _MAX_CONTEXT_TOKENS_ESTIMATE = 6000
    _llm_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm_")
    _NEGOTIATION_MAX_ROUNDS = 3

    @classmethod
    def _shutdown_executor(cls):
        cls._llm_executor.shutdown(wait=True)

    def __init__(self, psop: PSOP, agent_cards, runtime_intent: str = None, a2at_env_path: Path = None, lang: str = None):
        self.workflow = psop
        self.runtime_intent = runtime_intent
        self.lang = lang or "zh"
        self.current_step_idx = 0
        self.execution_history = []
        self.llm_client = get_llm_instance()
        self.agent_cards = agent_cards
        self._agent_map = {card.name: card for card in agent_cards if hasattr(card, 'name')}
        self._step_index = {s.name: i for i, s in enumerate(psop.steps)}
        self.push_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.step_outputs: Dict[str, Dict[str, Any]] = {}
        self.a2at_client = None
        self._httpx_client: Optional[httpx.AsyncClient] = None
        self.execution_context_id = ""
        self._auth_interceptors: Dict[str, List[Any]] = {}
        self._setup_agent_auth()

        if _A2AT_AVAILABLE:
            from common.a2at_config import get_a2at_env_path, update_a2at_language
            env_path = a2at_env_path or get_a2at_env_path()
            update_a2at_language(self.lang)
            try:
                self.a2at_client = A2ATClient(env_path=env_path)
                logger.info(f"DynamicWorkflowEngine initialized with A2ATClient, env_path={env_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize A2ATClient: {e}, continuing without negotiation support")
        else:
            logger.debug("a2a_t not available, negotiation support disabled")


    def _setup_agent_auth(self):
        auth_manager = get_auth_manager()
        for card in self.agent_cards:
            if not hasattr(card, 'name'):
                continue
            interceptors = []
            if card.security_schemes and card.security_requirements:
                cred_svc = auth_manager.get_service(card.name)
                if cred_svc is not None:
                    interceptors.append(AuthInterceptor(cred_svc))
                    logger.info(f"Agent '{card.name}' configured with AuthInterceptor")
                else:
                    logger.debug(f"Agent '{card.name}' has security schemes but no credentials configured, auth disabled")
            if getattr(card, 'capabilities', None) and card.capabilities.extensions:
                ext_uris = [ext.uri for ext in card.capabilities.extensions if ext.uri]
                if ext_uris:
                    interceptors.append(ExtensionInterceptor(ext_uris))
                    logger.info(f"Agent '{card.name}' configured with ExtensionInterceptor: {ext_uris}")
            if interceptors:
                self._auth_interceptors[card.name] = interceptors

    def set_push_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.push_callback = callback

    def _get_httpx_client(self) -> httpx.AsyncClient:
        if self._httpx_client is None:
            timeout_config = httpx.Timeout(connect=60, read=60, write=60, pool=10.0)
            self._httpx_client = httpx.AsyncClient(timeout=timeout_config, verify=False)
            auth_manager = get_auth_manager()
            auth_manager.set_httpx_client(self._httpx_client)
        return self._httpx_client

    async def _close_httpx_client(self):
        if self._httpx_client is not None:
            await self._httpx_client.aclose()
            self._httpx_client = None

    def _push_event(self, event_type: str, data: Dict[str, Any]):
        log_data = dict(data)
        for key in ("request", "response"):
            if isinstance(log_data.get(key), str):
                try:
                    log_data[key] = json.loads(log_data[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        try:
            serialized = json.dumps(log_data, indent=4, ensure_ascii=False, default=str)
        except Exception as e:
            logger.debug(f"Failed to serialize push event data: {e}")
            serialized = str(log_data)
        logger.info(f"push {event_type}:\n{serialized}")
        if self.push_callback:
            try:
                self.push_callback(event_type, data)
            except Exception as e:
                logger.error(f"Failed to push event: {e}")

    async def run(self):
        self.execution_context_id = str(uuid.uuid4())
        logger.info(f"Starting PSOP workflow, total {len(self.workflow.steps)} steps, context_id={self.execution_context_id}")
        pending = deque([i for i, s in enumerate(self.workflow.steps) if s.layer == 0 and not self._get_step_predecessors(s.name)])
        executed = set()
        defer_count = {}
        try:
            while pending:
                idx = pending.popleft()
                if idx >= len(self.workflow.steps) or idx in executed:
                    continue
                current_step = self.workflow.steps[idx]
                predecessors = self._get_step_predecessors(current_step.name)
                if not all(p in self.step_outputs for p in predecessors):
                    dc = defer_count.get(idx, 0) + 1
                    if dc > len(self.workflow.steps):
                        logger.warning(f"Step {current_step.name} waiting too long, skipping")
                        executed.add(idx)
                        continue
                    defer_count[idx] = dc
                    pending.append(idx)
                    await asyncio.sleep(0.05)
                    continue
                executed.add(idx)
                self.current_step_idx = idx
                current_step = self.workflow.steps[idx]
                logger.info(f"--- Executing step: {current_step.name} ---")

                step_result, success = await self._execute_subtasks(current_step)
                if not success:
                    logger.error(
                        f"Step {current_step.name} execution failed, stopping workflow.")
                    self._record_stop_event("Task execution failed", step_result)
                    break
                self.step_outputs[current_step.name] = step_result

                next_indices = await self._determine_next_steps(current_step, step_result)
                for nxt in reversed(next_indices):
                    if nxt not in executed and nxt not in pending:
                        pending.insert(0, nxt)
        except Exception as e:
            logger.critical(f"Unexpected exception occurred in engine: {e}", exc_info=True)
            raise
        finally:
            await self._close_httpx_client()

        return self.execution_history

    async def _determine_next_steps(self, step: Step, step_result: Dict[str, Any]) -> List[int]:
        if not step.next:
            return []
        if all(jc.condition == "" for jc in step.next):
            indices = []
            for jc in step.next:
                if jc.step in ("end", "retry", "endNode"):
                    continue
                tgt = self._find_step_index(jc.step)
                if tgt is not None:
                    indices.append(tgt)
            return indices
        next_name = await self._llm_route_decision(step, step_result)
        if next_name in ("end", "retry"):
            return []
        tgt = self._find_step_index(next_name)
        return [tgt] if tgt is not None else []

    def _get_interceptors(self, agent_name: str) -> list:
        return list(self._auth_interceptors.get(agent_name, []))

    def _get_task_t_uris(self, agent_card) -> list:
        uris = []
        if getattr(agent_card, 'capabilities', None) and agent_card.capabilities.extensions:
            for ext in agent_card.capabilities.extensions:
                if ext.uri and 'Task-T' in ext.uri:
                    uris.append(ext.uri)
        return uris

    def _extract_task_t_uri(self, agent_card) -> Optional[str]:
        uris = self._get_task_t_uris(agent_card)
        return uris[0] if uris else None

    async def send_message_to_agent(self, agent_name: str, task: str, httpx_client=None):
        return await self._send_with_negotiation(agent_name, task, httpx_client)

    async def _send_with_negotiation(self, agent_name: str, task: str, httpx_client=None, _round: int = 0):
        response_text, task_result, metadata_dict = await self._send_message_internal(
            agent_name, task, httpx_client
        )

        if task_result is not None and hasattr(task_result, 'status') and task_result.status:
            task_state = task_result.status.state
            from a2a.types import TaskState as TS
            if task_state == TS.TASK_STATE_INPUT_REQUIRED:
                if _round >= self._NEGOTIATION_MAX_ROUNDS:
                    logger.error(
                        f"Negotiation with agent '{agent_name}' reached max rounds ({self._NEGOTIATION_MAX_ROUNDS}) "
                        f"without convergence. Marking step as failed."
                    )
                    self._push_event("negotiation_failed", {
                        "agent": agent_name,
                        "response": json.dumps({
                            "type": "negotiation_failed",
                            "agent": agent_name,
                            "round": _round + 1,
                            "reason": f"Negotiation did not converge after {self._NEGOTIATION_MAX_ROUNDS} round(s)",
                        }, ensure_ascii=False),
                    })
                    raise RuntimeError(
                        f"Negotiation with agent '{agent_name}' did not converge after "
                        f"{self._NEGOTIATION_MAX_ROUNDS} round(s). Final agent response: {response_text[:300]}"
                    )
                logger.info(
                    f"Agent '{agent_name}' requested negotiation (round {_round + 1}/{self._NEGOTIATION_MAX_ROUNDS})"
                )
                self._push_negotiation_event(agent_name, metadata_dict, _round)
                resolved_task = await self._handle_agent_negotiation(
                    agent_name, task, metadata_dict
                )
                if resolved_task:
                    return await self._send_with_negotiation(
                        agent_name, resolved_task, httpx_client, _round + 1
                    )
                logger.warning(f"Failed to resolve negotiation for agent '{agent_name}', using partial response")

        if response_text is not None:
            return response_text
        return ""

    async def _send_message_internal(self, agent_name: str, task: str, httpx_client=None):
        agent_card = self._agent_map.get(agent_name)
        if not agent_card:
            raise RuntimeError(f"Agent not found: {agent_name}")

        task_text = task
        task_t_metadata = None
        task_t_uri = self._extract_task_t_uri(agent_card)
        skip_prompt_gen = False
        try:
            from common.negotiation_utils import is_follow_up_task
            skip_prompt_gen = is_follow_up_task(task)
        except ImportError:
            pass

        if self.a2at_client and not skip_prompt_gen:
            try:
                prompt_result = self.a2at_client.generate_task_prompt(task)
                if prompt_result.success and prompt_result.prompt_text:
                    if task_t_uri:
                        task_t_metadata = prompt_result.prompt_text
                        logger.info(f"[A2AT] Generated TASK-T prompt for agent '{agent_name}', will set in metadata")
                    else:
                        task_text = prompt_result.prompt_text
                        logger.info(f"[A2AT] Generated task prompt for agent '{agent_name}'")
                else:
                    logger.warning(f"[A2AT] Task prompt generation failed, using original task")
            except Exception as e:
                logger.warning(f"[A2AT] Failed to generate task prompt: {e}")

        try:
            client = httpx_client or self._get_httpx_client()
            config = ClientConfig(
                httpx_client=client,
                supported_protocol_bindings=[
                    "JSONRPC",
                    "HTTP+JSON",
                ],
                streaming=agent_card.capabilities.streaming if agent_card.capabilities else False,
            )
            client = ClientFactory(config).create(agent_card, interceptors=self._get_interceptors(agent_name))
            request_msg = new_text_message(
                text=task_text,
                context_id=self.execution_context_id,
            )
            if task_t_metadata and task_t_uri:
                from google.protobuf.struct_pb2 import Struct
                meta = Struct()
                meta.update({task_t_uri: task_t_metadata})
                request_msg.metadata.CopyFrom(meta)
                logger.info(f"[A2AT] Set TASK-T metadata on message for agent '{agent_name}'")
            send_req = SendMessageRequest(message=request_msg)
            send_req_json = MessageToJson(send_req, preserving_proto_field_name=True)
            try:
                req_payload = json.loads(send_req_json)
            except (json.JSONDecodeError, TypeError):
                req_payload = send_req_json
            self._push_event("agent_request", {
                "agent": agent_name,
                "request": req_payload
            })
            response_text = None
            last_response = None
            last_task_result = None
            last_metadata_dict = {}

            from a2a.types import Task, Message

            async for response in client.send_message(send_req):
                try:
                    raw_resp = MessageToJson(response, preserving_proto_field_name=True)
                    resp_payload = json.loads(raw_resp) if raw_resp != "{}" else raw_resp
                except Exception:
                    resp_payload = str(response)
                self._push_event("agent_response", {
                    "agent": agent_name,
                    "response": resp_payload
                })
                task_result = response.task
                message_result = response.message

                last_response = response
                last_task_result = task_result

                if (isinstance(task_result, Task)
                        or (hasattr(task_result, 'artifacts') and task_result.artifacts is not None
                            and hasattr(task_result, 'status'))):
                    if hasattr(task_result, 'artifacts') and task_result.artifacts:
                        for artifact in task_result.artifacts:
                            if hasattr(artifact, 'parts') and artifact.parts:
                                for part in artifact.parts:
                                    if hasattr(part, 'text') and part.text:
                                        response_text = (response_text or "") + part.text

                    if hasattr(task_result, 'metadata') and task_result.metadata:
                        metadata = task_result.metadata
                        if isinstance(metadata, dict):
                            metadata_dict = metadata
                        else:
                            metadata_dict = MessageToDict(metadata, preserving_proto_field_name=True)
                        last_metadata_dict = metadata_dict
                        if response_text is None and isinstance(metadata_dict, dict):
                            for key, val in metadata_dict.items():
                                if isinstance(val, str) and len(val) > 20:
                                    response_text = val
                                    logger.info(f"[{agent_name}] Extracted response text from task metadata key '{key}'")
                                    break
                        try:
                            from common.negotiation_utils import (
                                extract_negotiation_context_from_task_metadata,
                                log_negotiation_context,
                            )
                            negotiation_ctx = extract_negotiation_context_from_task_metadata(metadata_dict)
                            if negotiation_ctx:
                                log_negotiation_context(negotiation_ctx, f"[{agent_name}]")
                        except ImportError:
                            pass

                elif isinstance(message_result, Message):
                    if hasattr(message_result, 'parts') and message_result.parts:
                        for part in message_result.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text = (response_text or "") + part.text

            if response_text is not None:
                return response_text, last_task_result, last_metadata_dict
            elif last_response is not None:
                return str(last_response), last_task_result, last_metadata_dict
            else:
                raise RuntimeError("Agent completed but no response received")
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Agent call timed out") from e
        except httpx.ConnectError as e:
            raise RuntimeError(f"Failed to connect to Agent : {e}") from e
        except Exception as e:
            logger.error(f"Communicate with agent failed : {e}", exc_info=True)
            raise

    def _record_stop_event(self, reason, details):
        self.execution_history.append({
            "event": "STOPPED",
            "reason": reason,
            "details": details
        })

    def _push_negotiation_event(self, agent_name: str, metadata_dict: Dict[str, Any], round_num: int):
        concern = metadata_dict.get("negotiationConcern", "")
        context_data = metadata_dict.get("negotiationContext", {})
        self._push_event("negotiation_request", {
            "agent": agent_name,
            "response": json.dumps({
                "type": "negotiation_request",
                "agent": agent_name,
                "round": round_num + 1,
                "concern": concern or "(Agent expressed uncertainty about the task)",
                "negotiationType": context_data.get("negotiationType", "fulfillment") if isinstance(context_data, dict) else "fulfillment",
                "negotiationId": context_data.get("negotiationId", "") if isinstance(context_data, dict) else "",
            }, ensure_ascii=False),
        })

    async def _handle_agent_negotiation(
        self,
        agent_name: str,
        original_task: str,
        metadata_dict: Dict[str, Any],
    ) -> Optional[str]:
        if not self.a2at_client:
            logger.warning(f"Cannot handle negotiation: A2ATClient not available")
            return None

        from common.negotiation_utils import (
            extract_negotiation_content,
            build_negotiation_resolution_task,
            NEGOTIATION_CONTEXT_KEY,
            extract_original_task_from_follow_up,
        )

        # Strip any existing negotiation resolution markers to avoid recursive nesting
        clean_original = extract_original_task_from_follow_up(original_task) or original_task

        negotiation_text, context_data = extract_negotiation_content(metadata_dict)
        if not negotiation_text or not context_data:
            negotiation_concern = metadata_dict.get("negotiationConcern", "")
            if negotiation_concern:
                negotiation_text = negotiation_concern
            else:
                logger.warning(f"No negotiation content found in agent response metadata")
                return None

        logger.info(f"Processing negotiation from agent '{agent_name}': {negotiation_text[:150]}...")

        if not context_data:
            logger.info(f"No negotiation context in response, generating simple clarification")
            clarification = await self._generate_negotiation_clarification(
                agent_name=agent_name,
                original_task=clean_original,
                negotiation_text=negotiation_text,
                receive_message="",
            )
            if clarification:
                resolved = build_negotiation_resolution_task(clean_original, clarification)
                self._push_event("negotiation_resolved", {
                    "agent": agent_name,
                    "response": json.dumps({
                        "type": "negotiation_resolved",
                        "agent": agent_name,
                        "round": 0,
                        "clarification": clarification,
                        "originalTask": original_task,
                    }, ensure_ascii=False),
                })
                return resolved
            self._push_event("negotiation_failed", {
                "agent": agent_name,
                "response": json.dumps({
                    "type": "negotiation_failed",
                    "agent": agent_name,
                    "reason": "Failed to generate clarification",
                }, ensure_ascii=False),
            })
            return None

        try:
            receive_result = self.a2at_client.receive_negotiation(
                message=negotiation_text,
                context=context_data,
            )
        except Exception as e:
            logger.warning(f"Failed to receive negotiation: {e}")
            return None

        need_response = receive_result.get("needResponse", False)
        logger.info(
            f"Negotiation receive result: needResponse={need_response}, "
            f"message={receive_result.get('message', '')[:100]}"
        )

        if not need_response:
            self._push_event("negotiation_failed", {
                "agent": agent_name,
                "response": json.dumps({
                    "type": "negotiation_failed",
                    "agent": agent_name,
                    "reason": f"Agent did not require a response (needResponse=false)",
                }, ensure_ascii=False),
            })
            return None

        clarification = await self._generate_negotiation_clarification(
            agent_name=agent_name,
            original_task=clean_original,
            negotiation_text=negotiation_text,
            receive_message=receive_result.get("message", ""),
        )

        if not clarification:
            logger.warning(f"Failed to generate negotiation clarification")
            self._push_event("negotiation_failed", {
                "agent": agent_name,
                "response": json.dumps({
                    "type": "negotiation_failed",
                    "agent": agent_name,
                    "reason": "LLM clarification generation failed",
                }, ensure_ascii=False),
            })
            return None

        from a2a_t.negotiation.common.enums import NegotiationStatus
        from a2a_t.negotiation.common.models import ContinueNegotiationInput, NegotiationContext

        context_obj = NegotiationContext.from_context(context_data)
        continued_context_data = None
        try:
            continue_result = self.a2at_client.continue_negotiation(
                ContinueNegotiationInput(
                    context=context_obj,
                    status=NegotiationStatus.AGREED,
                    content_text=clarification,
                )
            )
            logger.info(f"Negotiation continued successfully, round={context_obj.round + 1}")
            continued_context_data = continue_result.get(NEGOTIATION_CONTEXT_KEY)
        except Exception as e:
            logger.error(f"Failed to continue negotiation: {e}")
            self._push_event("negotiation_failed", {
                "agent": agent_name,
                "response": json.dumps({
                    "type": "negotiation_failed",
                    "agent": agent_name,
                    "reason": f"continue_negotiation failed: {e}",
                }, ensure_ascii=False),
            })
            return None

        resolved_task = build_negotiation_resolution_task(
            clean_original, clarification,
            continued_context=continued_context_data,
        )
        self._push_event("negotiation_resolved", {
            "agent": agent_name,
            "response": json.dumps({
                "type": "negotiation_resolved",
                "agent": agent_name,
                "round": context_obj.round + 1,
                "clarification": clarification,
                "originalTask": original_task,
            }, ensure_ascii=False),
        })
        return resolved_task

    async def _generate_negotiation_clarification(
        self,
        agent_name: str,
        original_task: str,
        negotiation_text: str,
        receive_message: str,
    ) -> Optional[str]:
        if not self.llm_client:
            return f"Engine received your negotiation request and has reviewed the execution context. Please proceed with the original task using the clarification above. If you have specific questions, state them clearly."

        workflow_context = self._build_clarification_context()
        lang_hint = "Respond in Chinese." if self.lang == "zh" else "Respond in English."

        prompt = f"""# Role
You are the orchestration engine's negotiation handler. An agent expressed uncertainty
or confusion about a task you assigned. Based on the completed workflow execution
context below, provide an accurate clarification or supplementary explanation.

# Important Constraints
- You may ONLY base your answer on the actual outputs in the "Executed Workflow Context" below.
  **Do NOT fabricate or speculate about facts that have not occurred.**
- If the context is insufficient to answer the agent's concern, tell the agent directly:
  "Insufficient information available. Please do your best with what you have."
- Be concise and focused on the specific concern the agent raised.

# Workflow Goal
{self.runtime_intent or "(not specified)"}

# Executed Workflow Context (completed steps and their outputs)
{workflow_context}

# Current Agent
{agent_name}

# Original Task
{original_task}

# Agent's Negotiation Request (the concern or question)
{negotiation_text}

# Supplementary Notes
{receive_message}

# Task
Based on the execution context above, provide a clear clarification to the agent.
Do NOT add any prefix markers like "Clarification:". {lang_hint}"""

        try:
            _, clarification = await asyncio.get_event_loop().run_in_executor(
                DynamicWorkflowEngine._llm_executor,
                self.llm_client.ask_llm,
                prompt,
            )
            clarification = clarification.strip() if clarification else ""
            if clarification:
                logger.info(f"Generated negotiation clarification for '{agent_name}': {clarification[:150]}...")
                return clarification
        except Exception as e:
            logger.error(f"LLM clarification failed: {e}")

        return "Engine received your negotiation request. Please re-attempt the original task. If you have specific questions, state them clearly."

    def _build_clarification_context(self) -> str:
        if not self.step_outputs:
            return "(no completed steps yet)"

        parts = []
        for i, step in enumerate(self.workflow.steps):
            if step.name not in self.step_outputs:
                continue
            outputs = self.step_outputs[step.name]
            parts.append(f"### {step.name}")
            for task_desc, output in outputs.items():
                text = output if isinstance(output, str) else str(output)
                parts.append(f"- Task: {task_desc}")
                parts.append(f"  Output: {text}")
        return "\n".join(parts) if parts else "(no completed steps yet)"

    async def _execute_subtasks(self, step: Step) -> tuple[Dict[str, Any], bool]:
        results = {}
        context_message = self._build_context_for_step(step)

        async def execute_single_task(task: Task) -> tuple[str, str, bool]:
            try:
                logger.info(f"   > Calling Agent: {task.agent}, Skill: {task.skill}, Desc: {task.description}")
                task_message = self._build_task_message(task, context_message)
                raw_output = await self.send_message_to_agent(task.agent, task_message)
                task.status = TaskStatus.SUCCESS
                self._push_psop_update()
                self.execution_history.append({
                    "step": step.name,
                    "task": task.description,
                    "status": "success",
                    "output": raw_output
                })
                return task.description, raw_output, True
            except Exception as e:
                task.status = TaskStatus.FAILED
                error_msg = f"Agent call failed : {str(e)}"
                logger.error(f"  >Task failed: {task.description} | Error: {error_msg}")
                self._push_psop_update()
                self.execution_history.append({
                    "step": step.name,
                    "task": task.description,
                    "status": "failed",
                    "output": error_msg
                })
                return task.description, {"error": error_msg}, False

        if step.type == StepType.ANY_SUCCESS:
            coros = [execute_single_task(task) for task in step.subtasks]
            for coro in asyncio.as_completed(coros):
                task_name, output, success = await coro
                results[task_name] = output
                if success:
                    return results, True
            self._record_stop_event("ANY_SUCCESS: all subtasks failed", results)
            return results, False

        gathered = await asyncio.gather(*[execute_single_task(task) for task in step.subtasks])
        failed = False
        for task_name, output, success in gathered:
            results[task_name] = output
            if not success:
                failed = True
        return results, not failed

    def _push_psop_update(self):
        try:
            psop_data = (
                self.workflow.model_dump_json()
                if hasattr(self.workflow, 'model_dump_json')
                else self.workflow.model_dump()
            )
        except Exception as e:
            logger.warning(f"Failed to serialize PSOP for event push: {e}")
            psop_data = str(self.workflow)
        self._push_event("psop_update", {"psop": psop_data})

    def _get_step_predecessors(self, step_name: str) -> List[str]:
        predecessors = []
        for s in self.workflow.steps:
            if s.next:
                for jc in s.next:
                    if jc.step == step_name:
                        predecessors.append(s.name)
                        break
        return predecessors

    def _get_all_predecessors(self, step_name: str) -> List[str]:
        ancestors = set()
        queue = deque([step_name])
        while queue:
            current = queue.popleft()
            for s in self.workflow.steps:
                if s.next:
                    for jc in s.next:
                        if jc.step == current and s.name not in ancestors:
                            ancestors.add(s.name)
                            queue.append(s.name)
        return list(ancestors)

    def _build_context_for_step(self, step: Step) -> str:
        if step.layer <= 0:
            if self.runtime_intent:
                return f"## Runtime Context\n\nUser's original intent and scenario description:\n{self.runtime_intent}"
            return ""
        parts = []
        if self.runtime_intent:
            parts.append(f"## Runtime Context\n\nUser's original intent and scenario description:\n{self.runtime_intent}")
        parts.append("## Previous Step Execution Results\n")
        if step.context_from and "*" in step.context_from:
            all_predecessors = self._get_all_predecessors(step.name)
            ref_pairs = [(name, self.step_outputs[name])
                         for name in all_predecessors if name in self.step_outputs]
        elif step.context_from:
            ref_pairs = [(name, self.step_outputs[name])
                         for name in step.context_from if name in self.step_outputs]
        else:
            predecessor_names = self._get_step_predecessors(step.name)
            ref_pairs = [(name, self.step_outputs[name])
                         for name in predecessor_names if name in self.step_outputs]

        total_chars = 0
        for ref_step_name, ref_results in ref_pairs:
            step_header = f"### {ref_step_name} Results\n"
            parts.append(step_header)
            total_chars += len(step_header)
            for task_desc, output in ref_results.items():
                text = output if isinstance(output, str) else str(output)
                entry = f"**Input (Task)**: {task_desc}\n**Output (Result)**: {text}\n\n"
                parts.append(entry)
                total_chars += len(entry)
        return "\n".join(parts).strip()

    def _build_task_message(self, task: Task, context_message: str) -> str:
        lang_hint = ""
        if self.lang == "en":
            lang_hint = "\n\nPlease respond in English."
        elif self.lang == "zh":
            lang_hint = "\n\n请用中文回复。"
        if context_message:
            return f"{context_message}\n\n## Current Task\n{task.description}{lang_hint}"
        return f"{task.description}{lang_hint}"

    async def _llm_route_decision(self, current_step: Step, task_result: Dict[str, Any]) -> str:
        results_context = []
        for skill, res in task_result.items():
            if isinstance(res, dict) and "error" in res:
                results_context.append(f"[{skill}]: Execution failed - {res['error']}")
            else:
                text_res = res if isinstance(res, str) else str(res)
                results_context.append(f"[{skill}]: Execution succeeded - Output summary: {text_res}")
        results_text = "\n".join(results_context)
        next_conditions = json.dumps(
            [{"step": c.step, "condition": c.condition} for c in (current_step.next or [])],
            ensure_ascii=False,
            indent=2,
        )
        prompt_template = f"""
# Role
You are a workflow logic controller. Your task is to determine the next step of the
workflow based on the task execution results and predefined conditions.

# Current Context
Current step: {current_step.name}
Step type: {current_step.type.value}

# Execution Results (Previous Step Output)
{results_text}

# Next Conditions (Required for Transition)
{next_conditions}

# Decision Logic
1. Analyze the Execution Results above.
2. Check whether any of the Next Conditions' "condition" descriptions are satisfied.
   - If a condition says e.g. "xx succeeded", check the results for evidence that xx succeeded.
   - An empty condition ('""') typically means unconditional transition to the next step.
3. If a condition is met, output the corresponding target step name.
4. If no condition is met, or the task execution contains an error, output "end".
5. If the result is ambiguous but appears successful, output "retry" to request manual intervention.

# Output Format
- Output exactly one word or phrase: the target step name (e.g. "step2"), "end", or "retry".
- Do NOT output any explanation, punctuation, or other characters.
"""
        if not self.llm_client:
            raise ValueError("LLM Client not initialized. Please set engine.llm_client.")
        try:
            _, decision = await asyncio.get_event_loop().run_in_executor(
                DynamicWorkflowEngine._llm_executor, self.llm_client.ask_llm, prompt_template
            )
            decision = decision.strip() if decision else ""
            if not decision:
                logger.error(f"LLM returned empty decision for step '{current_step.name}', defaulting to termination.")
                return "end"
            logger.info(f"LLM route decision for step '{current_step.name}': raw='{decision}', conditions={next_conditions}")
            if decision in ["end", "retry"]:
                return decision
            allowed_next = [jc.step for jc in (current_step.next or [])]
            allowed_lower = {n.lower(): n for n in allowed_next}
            if decision in allowed_next:
                return decision
            if decision.lower() in allowed_lower:
                logger.info(f"LLM step name '{decision}' case-normalized to '{allowed_lower[decision.lower()]}'")
                return allowed_lower[decision.lower()]
            else:
                logger.warning(f"LLM returned step '{decision}' not in declared next {allowed_next}, defaulting to termination.")
                return "end"
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return "end"

    def _find_step_index(self, step_name: str) -> Optional[int]:
        return self._step_index.get(step_name)

atexit.register(DynamicWorkflowEngine._shutdown_executor)

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
1. Uses the caller-selected PSOP, or searches by intent when none is supplied
2. Sends the intent and selected PSOP snapshot to the Workbench Agent via A2A-T
3. Streams back SDK events from TaskUpdate metadata to the frontend SSE

All workflow execution logic (ControlPoint, extension pre-positioning,
agent card loading) lives in the Workbench Agent.
"""

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

from a2a.types import Part
from loguru import logger
from pydantic import ValidationError
from workflow_engine import A2ATransport, MessageContent, WorkflowEngineClient

from host_agent.dispatch_auth import PROOF_KEY, DispatchValidationError, sign_dispatch
from orchestrate.core.catalog_gate import has_role_tasks
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_execution_snapshot import binding_metadata
from orchestrate.core.shared_handlers import SharedHandlers
from orchestrate.persistence.errors import RoleReferenceError
from orchestrate.runtime.instance_projection import (
    ResolutionError, ResolutionRequest, resolve_execution_plan,
)

try:
    from a2a_t.llm.factory import LLMClientFactory as _LLMFactory
    from a2a_t.llm.providers.openai import OpenAIClient as _OpenAIClient
    _LLMFactory.register("deepseek", _OpenAIClient)
except Exception:
    pass


_CODE_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _resolution_error_event(error) -> dict:
    message = str(error)
    code = getattr(error, "code", None) or message.split(":", 1)[0]
    if not _CODE_PREFIX_PATTERN.match(code):
        code = "RESOLUTION_FAILED"
    data = {"error": message, "code": code}
    for key in ("task_ids", "binding_group", "exclusions", "candidates", "reason", "instance_id", "role_ids"):
        value = getattr(error, key, None)
        if value:
            data[key] = value
    return {"type": "error", "data": data, "timestamp": time.time()}


def _resolution_event_data(snapshot) -> dict:
    scope = snapshot.context.scope
    return {
        "execution_id": snapshot.execution_id,
        "catalog_version": snapshot.catalog_version,
        "config_version": snapshot.config_version,
        "policy_version": snapshot.policy_version,
        "execution_scope": f"{scope.tenant}/{scope.site}/{scope.business_object}",
        "bindings": [b.model_dump(mode="json") for b in snapshot.bindings],
        "card_fingerprints": [c.fingerprint for c in snapshot.cards],
        "template_fingerprint": snapshot.template_fingerprint,
        "snapshot_fingerprint": snapshot.fingerprint,
        "resolution_snapshot": snapshot.model_dump(mode="json"),
    }


def _role_dispatch_metadata(snapshot) -> dict:
    """A2A-T metadata keys that bind the dispatch to its frozen resolution evidence."""
    return {
        "__orch_binding__": json.dumps(binding_metadata(snapshot), ensure_ascii=False),
        "__orch_cards__": snapshot.model_dump_json(),
    }


class OrchestrationEngine:
    """Thin orchestration channel -- PSOP preview + A2A-T dispatch + event forward."""

    def __init__(self, agent_cards, target_agent: str = None, lang: str = None, *, select_template: bool = True):
        from common.util.config_util import get_conf

        self.lang = lang or "zh"
        self._agent_cards = agent_cards
        self._select_template = select_template
        conf = get_conf()
        self._target_agent = target_agent or conf.get("workflow_host_agent_name", "Host Agent")
        self._target_organization = conf.get("workflow_host_agent_organization") or None

        self._ssl_verify = str(conf.get("client_verify_server", "true")).lower() == "true"

        configured_path = os.environ.get("ORCH_AGENT_CREDENTIALS_FILE") or conf.get("agent_credentials_file")
        self._cred_path = None
        if configured_path:
            cred_path = Path(configured_path)
            if not cred_path.is_absolute():
                cred_path = Path(__file__).resolve().parent.parent.parent / cred_path
            if not cred_path.is_file():
                raise ValueError("Configured agent credentials file does not exist")
            self._cred_path = str(cred_path)

    def _find_target_card(self):
        if not self._target_agent:
            return None
        matches = [
            card for card in self._agent_cards
            if card.name == self._target_agent and (
                self._target_organization is None
                or card.provider.organization == self._target_organization
            )
        ]
        if len(matches) > 1:
            raise ResolutionError(
                "HOST_AGENT_AMBIGUOUS",
                f"Multiple cards match Host Agent '{self._target_agent}'. Configure a unique organization and name.",
            )
        return matches[0] if matches else None

    def _get_engine_client(self) -> WorkflowEngineClient:
        target_card = self._find_target_card()
        if target_card is None:
            raise ResolutionError("HOST_AGENT_NOT_FOUND", f"Agent '{self._target_agent}' not found in registry")
        transport = A2ATransport(
            agent_cards=[target_card],
            credentials_config=self._cred_path,
            ssl_verify=self._ssl_verify,
        )
        return WorkflowEngineClient.owning(transport, max_negotiation_exchanges=3)

    async def events(
        self, intent: str, *, psop: PSOP | None = None,
        resolution_request: ResolutionRequest | None = None,
        execution_id: str | None = None,
        dispatch_guard=None,
        transport_observer=None,
    ) -> AsyncIterator[dict]:
        """Relay an explicit snapshot, or select by intent if none was supplied.

        Role-bound workflows are resolved against the approved catalog and
        instance registry first: a ``resolution`` event carries the frozen
        plan, and dispatch metadata binds the execution copy to its evidence.
        Resolution failures yield one structured ``error`` event and never
        reach transport.
        """
        psop_model = psop.model_copy(deep=True) if psop is not None else None
        resolution_snapshot = None
        if psop_model is None and getattr(self, "_select_template", True):
            yield {
                "type": "start",
                "data": {"workflow": intent[:80], "intent": intent, "phase": "searching", "target_agent": self._target_agent},
                "timestamp": time.time(),
            }
            logger.info("[Orchestration] Searching PSOP for target agent {}", self._target_agent)
            retrieval = SharedHandlers.retrieval()
            results = await asyncio.to_thread(retrieval.retrieve_psop_by_intent_topn, intent, 3)
            if results:
                psop_id = results[0].workflow_id
                yield {
                    "type": "start",
                    "data": {"workflow": results[0].name or psop_id, "workflow_id": psop_id, "phase": "loading"},
                    "timestamp": time.time(),
                }
                loaded = await asyncio.to_thread(retrieval.get_psop_by_id, psop_id)
                if loaded is not None:
                    psop_model = loaded.model_copy(deep=True)
                else:
                    yield _resolution_error_event(ResolutionError("PSOP_NOT_FOUND", "Selected workflow cannot be loaded"))
                    return
            else:
                yield _resolution_error_event(ResolutionError("PSOP_NOT_FOUND", "No matching workflow found"))
                return
        elif psop_model is not None:
            yield {
                "type": "start",
                "data": {"workflow": psop_model.name, "workflow_id": psop_model.id, "phase": "loading"},
                "timestamp": time.time(),
            }

        if psop_model is not None:
            yield {
                "type": "psop_update",
                "data": {"psop": psop_model.model_dump(mode="json")},
                "timestamp": time.time(),
            }

        if psop_model is not None and has_role_tasks(psop_model):
            try:
                resolution_snapshot = resolve_execution_plan(
                    psop_model, resolution_request, self._agent_cards,
                    **({"execution_id": execution_id} if execution_id is not None else {}),
                )
            except ValidationError:
                error = DispatchValidationError("Invalid frozen execution snapshot", reason="ENVELOPE_SCHEMA")
                logger.warning("[RoleDispatch] rejected psop_id={} reason={}", psop_model.id, error.reason)
                yield _resolution_error_event(error)
                return
            except (ResolutionError, RoleReferenceError, ValueError) as error:
                logger.warning(
                    "[Orchestration] Role resolution failed for workflow id={}: {}",
                    psop_model.id, error,
                )
                yield _resolution_error_event(error)
                return
            # Live status updates must not mutate the authenticated evidence.
            psop_model = resolution_snapshot.execution_psop.model_copy(deep=True)
            logger.info(
                "[RoleDispatch] resolved execution_id={} psop_id={} catalog_version={} task_ids={} instance_ids={}",
                resolution_snapshot.execution_id, psop_model.id, resolution_snapshot.catalog_version,
                [binding.task_id for binding in resolution_snapshot.bindings],
                [card.instance_id for card in resolution_snapshot.cards],
            )
            yield {
                "type": "resolution",
                "data": _resolution_event_data(resolution_snapshot),
                "timestamp": time.time(),
            }
            yield {
                "type": "psop_update",
                "data": {"psop": psop_model.model_dump(mode="json")},
                "timestamp": time.time(),
            }

        # Defense in depth: unresolved role IDs must never reach transport.
        if psop_model and any(
            task.binding == "role" for step in psop_model.steps for task in step.subtasks
        ):
            logger.warning(
                "[Orchestration] Refusing to dispatch unresolved role workflow "
                "id={} name={!r}: role instance resolution is not enabled yet",
                psop_model.id, psop_model.name,
            )
            raise ValueError("ROLE_EXECUTION_NOT_ENABLED: unresolved role workflow")

        dispatch_metadata = {}
        if psop_model:
            dispatch_metadata["__orch_psop_id__"] = psop_model.id
            dispatch_metadata["__orch_psop__"] = json.dumps(
                psop_model.model_dump(mode="json"),
                ensure_ascii=False,
            )
            logger.info(f"[Orchestration] Passing psop_id={psop_model.id} to target agent")

        if resolution_snapshot is not None:
            dispatch_metadata.update(_role_dispatch_metadata(resolution_snapshot))
            try:
                dispatch_metadata[PROOF_KEY] = sign_dispatch(
                    dispatch_metadata, os.environ.get("ORCH_ROLE_DISPATCH_KEY", ""),
                    intent=intent,
                )
            except DispatchValidationError as error:
                logger.warning("[RoleDispatch] rejected execution_id={} psop_id={} reason={}",
                               resolution_snapshot.execution_id, psop_model.id, error.reason)
                yield _resolution_error_event(error)
                return

        try:
            engine_client = self._get_engine_client()
        except ResolutionError as error:
            yield _resolution_error_event(error)
            return

        try:
            if dispatch_guard is not None:
                # Freeze the actual outbound envelope before the first network send.
                await dispatch_guard({
                    "psop": psop_model.model_dump(mode="json") if psop_model else None,
                    "metadata": {key: value for key, value in dispatch_metadata.items() if key != PROOF_KEY},
                    "resolution_snapshot": (
                        resolution_snapshot.model_dump(mode="json")
                        if resolution_snapshot is not None else None
                    ),
                    "target_agent": self._target_agent,
                })
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
            logger.info("[Orchestration] Dispatching to target agent {}", self._target_agent)
            content = MessageContent(
                parts=(Part(text=intent),),
                metadata=dispatch_metadata,
            )
            terminal_emitted = False
            async for response in engine_client.stream_message(
                self._target_agent, content,
            ):
                if transport_observer is not None:
                    task_id = getattr(response, "task_id", "")
                    if isinstance(task_id, str) and task_id:
                        await transport_observer({"task_id": task_id,
                            "context_id": getattr(response, "context_id", ""),
                            "task_state": str(response.task_state or "")})
                sdk_event_json = response.metadata.get("__sdk_event__")
                if sdk_event_json:
                    try:
                        event = json.loads(sdk_event_json)
                        if event.get("type") in {"complete", "error", "cancelled"}:
                            terminal_emitted = True
                        if event.get("type") == "task_status_changed" and psop_model:
                            for shaped in self._shape_psop_update(event, psop_model):
                                yield shaped
                        else:
                            yield event
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"[Orchestration] Failed to parse __sdk_event__: {e}")
                else:
                    task_state = str(response.task_state or "").upper()
                    if "CANCEL" in task_state:
                        yield {"type": "cancelled", "data": {"reason": "Host Agent task cancelled"}, "timestamp": time.time()}
                    elif "FAILED" in task_state or "REJECTED" in task_state:
                        yield {"type": "error", "data": {"error": "Host Agent task failed"}, "timestamp": time.time()}
                    elif "COMPLETED" in task_state and not terminal_emitted:
                        terminal_emitted = True
                        yield {"type": "complete", "data": {}, "timestamp": time.time()}

        except Exception as e:
            logger.error(f"[Orchestration] Workflow execution failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"error": str(e), "dispatch_outcome": "unknown"},
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

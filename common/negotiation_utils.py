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

from typing import Dict, Any, Optional
from loguru import logger

from a2a_t.negotiation.common.enums import NegotiationType, NegotiationStatus, NegotiationRole
from a2a_t.negotiation.common.models import NegotiationContext


NEGOTIATION_TEXT_KEY = "https://github.com/a2aproject/telecommunication/extensions/NEGOTIATION-T"
NEGOTIATION_CONTEXT_KEY = "https://github.com/a2aproject/telecommunication/extensions/DATA-NEGOTIATION-T/v1"
TASK_PROMPT_KEY = "https://github.com/a2aproject/telecommunication/extensions/Task-T/v1"

NEGOTIATION_RESOLUTION_MARKER = "[NEGOTIATION_RESOLUTION]"
NEGOTIATION_REQUEST_MARKER = "[NEGOTIATION_REQUEST]"
NEGOTIATION_CONTEXT_MARKER = "[NEGOTIATION_CONTEXT]"
_NEGOTIATION_MAX_ROUNDS = 5


def extract_negotiation_context_from_task_metadata(
    task_metadata: Dict[str, Any]
) -> Optional[NegotiationContext]:
    if not task_metadata:
        return None

    context_data = task_metadata.get("negotiationContext")
    if not context_data:
        return None

    try:
        return NegotiationContext.from_context(context_data)
    except Exception as e:
        logger.error(f"Failed to parse negotiation context: {e}")
        return None


def extract_negotiation_context_from_artifact_metadata(
    artifact_metadata: Dict[str, Any]
) -> Optional[NegotiationContext]:
    if not artifact_metadata:
        return None

    context_data = artifact_metadata.get("negotiationContext")
    if not context_data:
        return None

    try:
        return NegotiationContext.from_context(context_data)
    except Exception as e:
        logger.error(f"Failed to parse negotiation context from artifact: {e}")
        return None


def build_negotiation_metadata(
    negotiation_result: Dict[str, Any]
) -> Dict[str, Any]:
    context_data = negotiation_result.get(NEGOTIATION_CONTEXT_KEY)
    if not context_data:
        logger.warning("No negotiation context in result")
        return {}

    return {"negotiationContext": context_data}


def is_negotiation_in_progress(context: NegotiationContext) -> bool:
    return context.status == NegotiationStatus.IN_PROGRESS


def is_negotiation_agreed(context: NegotiationContext) -> bool:
    return context.status == NegotiationStatus.AGREED


def is_negotiation_rejected(context: NegotiationContext) -> bool:
    return context.status == NegotiationStatus.REJECTED


def get_negotiation_round(context: NegotiationContext) -> int:
    return context.round


def get_negotiation_type(context: NegotiationContext) -> NegotiationType:
    return context.negotiation_type


def log_negotiation_context(context: NegotiationContext, prefix: str = "") -> None:
    logger.info(
        f"{prefix} Negotiation context: "
        f"type={context.negotiation_type.value}, "
        f"id={context.negotiation_id}, "
        f"role={context.role.value}, "
        f"round={context.round}, "
        f"status={context.status.value}"
    )


def is_uncertain_response(response_text: str, llm_client=None) -> bool:
    if not response_text:
        return False
    if llm_client is None:
        try:
            from common.llm import get_llm_instance
            llm_client = get_llm_instance()
        except Exception:
            return False
    if llm_client is None:
        return False

    prompt = f"""# Role
You are a task completion quality detector. Determine whether the following agent
response indicates the agent was **unable to complete** the task or **needs help,
more information, or clarification**.

# Agent Response
{response_text}

# Judgment Rules
- If the response expresses confusion, uncertainty, inability to proceed, or explicitly
  asks for more information → reply YES
- If the response normally completes the task, provides analysis results, or offers
  actionable suggestions → reply NO
- If the response is vague but makes a partial attempt to answer → reply NO

# Output Format
Reply with exactly one word: YES or NO."""
    try:
        _, decision = llm_client.ask_llm(prompt)
        decision = decision.strip().upper() if decision else "NO"
        return decision.startswith("YES")
    except Exception:
        return False


def extract_negotiation_content(task_metadata: Dict[str, Any]) -> tuple[Optional[str], Optional[dict]]:
    if not task_metadata:
        return None, None
    negotiation_text = task_metadata.get("negotiationText")
    context_data = task_metadata.get("negotiationContext")
    return negotiation_text, context_data


def build_negotiation_resolution_task(
    original_task: str,
    resolution_text: str,
    continued_context: Optional[dict] = None,
) -> str:
    parts = [
        f"{NEGOTIATION_RESOLUTION_MARKER}",
        f"The engine has reviewed your negotiation request and provides the following clarification:",
        "",
        f"{resolution_text}",
        "",
        f"---",
        f"Original Task:",
        f"{original_task}",
        "",
        f"Please re-execute the task based on the clarification above.",
    ]
    if continued_context:
        import json as _json
        parts.append("")
        parts.append(NEGOTIATION_CONTEXT_MARKER)
        parts.append(_json.dumps(continued_context, ensure_ascii=False))
    return "\n".join(parts)


def is_follow_up_task(task_text: str) -> bool:
    return NEGOTIATION_RESOLUTION_MARKER in task_text


def extract_original_task_from_follow_up(task_text: str) -> Optional[str]:
    marker = f"{NEGOTIATION_RESOLUTION_MARKER}\n"
    if marker not in task_text:
        return None
    parts = task_text.split("Original Task:\n", 1)
    if len(parts) < 2:
        return None
    original = parts[1].split("\n\nPlease re-execute the task based on the clarification above.", 1)[0]
    return original.strip()


def extract_continued_context_from_follow_up(task_text: str) -> Optional[dict]:
    marker = f"{NEGOTIATION_CONTEXT_MARKER}\n"
    if marker not in task_text:
        return None
    try:
        import json as _json
        context_json = task_text.split(marker, 1)[1].strip()
        if "\n" in context_json:
            context_json = context_json.split("\n", 1)[0].strip()
        return _json.loads(context_json)
    except Exception:
        return None


def cleanup_negotiation_resolution_marker(task_text: str) -> str:
    for marker in (NEGOTIATION_CONTEXT_MARKER, NEGOTIATION_RESOLUTION_MARKER):
        if marker not in task_text:
            continue
        parts = task_text.split(marker, 1)
        body = parts[0] if len(parts) > 1 else ""
        if len(parts) > 1:
            rest = parts[1]
            if "\nPlease re-execute the task based on the clarification above.\n" in rest:
                rest = rest.split("\nPlease re-execute the task based on the clarification above.\n", 1)[0]
            if "\nOriginal Task:\n" in rest:
                rest = rest.split("\nOriginal Task:\n", 1)[0]
        task_text = body.strip() + "\n\nPlease re-execute the task based on the clarification above."
        break
    return task_text.strip()

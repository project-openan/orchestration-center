# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Host-side adaptation of the shared wire contract to actual AgentCards."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from a2a.types import AgentCard
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from pydantic import ValidationError

from host_agent.dispatch_auth import DispatchValidationError
from host_agent.role_contract import RoleSnapshot, content_digest


def read_role_snapshot(metadata: Mapping[str, Any], workflow: dict) -> RoleSnapshot:
    """Read authenticated metadata without exposing raw schema errors to users."""
    try:
        snapshot = RoleSnapshot.model_validate_json(metadata["__orch_cards__"])
        if json.loads(metadata["__orch_binding__"]) != snapshot.binding_metadata():
            raise DispatchValidationError("Binding projection differs from snapshot", reason="BINDING_PROJECTION")
        if metadata["__orch_psop_id__"] != snapshot.template["id"] or workflow != snapshot.execution_psop:
            raise DispatchValidationError("Execution workflow differs from snapshot", reason="EXECUTION_COPY")
        return snapshot
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            cause = error.get("ctx", {}).get("error")
            if isinstance(cause, DispatchValidationError):
                raise cause from exc
        raise DispatchValidationError("Invalid role snapshot schema", reason="ENVELOPE_SCHEMA") from exc
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DispatchValidationError):
            raise
        raise DispatchValidationError("Invalid role snapshot metadata", reason="ENVELOPE_SCHEMA") from exc


def validated_agent_cards(snapshot: RoleSnapshot, current_cards: Sequence[AgentCard]) -> list[AgentCard]:
    """Compare current cards, then reconstruct selected cards from frozen data."""
    if not isinstance(current_cards, Sequence) or not all(isinstance(card, AgentCard) for card in current_cards):
        raise DispatchValidationError("Invalid current AgentCard collection", reason="REGISTRY_SCHEMA")
    selected_names = {card.agent_name for card in snapshot.cards}
    for frozen in snapshot.cards:
        matching = [card for card in current_cards if card.name == frozen.agent_name]
        if not matching:
            reason = "REGISTRY_CARD_MISSING"
        elif len(matching) > 1:
            reason = "REGISTRY_NAME_COLLISION"
        else:
            reason = "REGISTRY_CARD_DRIFT"
        if len(matching) != 1 or frozen.fingerprint != content_digest(MessageToDict(matching[0])):
            affected = [binding for binding in snapshot.bindings if binding.instance_id == frozen.instance_id]
            raise DispatchValidationError("Selected registry card missing, ambiguous, or changed", reason=reason,
                task_ids=tuple(binding.task_id for binding in affected), instance_id=frozen.instance_id,
                role_ids=tuple(sorted({binding.role_id for binding in affected})))
    try:
        selected = [ParseDict(card.card, AgentCard()) for card in snapshot.cards]
    except ParseError as exc:
        raise DispatchValidationError("Invalid frozen AgentCard", reason="CARD_SCHEMA") from exc
    return selected + [card for card in current_cards if card.name not in selected_names]


def validate_role_snapshot(metadata: Mapping[str, Any], workflow: dict,
                           current_cards: Sequence[AgentCard]) -> list[AgentCard]:
    """Compatibility facade; callers authenticate metadata before validation."""
    return validated_agent_cards(read_role_snapshot(metadata, workflow), current_cards)

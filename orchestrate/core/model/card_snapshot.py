# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Frozen AgentCard snapshots: the dispatch-time transport contract.

A snapshot is the complete AgentCard content bound to one instance identity.
The fingerprint covers the entire card, so any drift (skills, endpoints,
extensions, security) changes the digest and fails the snapshot check.
Snapshots are produced by a trusted card adapter and consumed by the Host
Agent; they never come from an execution request.
"""

import hashlib
import json
from typing import Any

from pydantic import model_validator

from orchestrate.core.model.role_catalog import CatalogModel, Identifier


def canonical_card_json(card: dict[str, Any]) -> str:
    """Stable canonical form: sorted keys, no insignificant whitespace, non-ASCII preserved."""
    return json.dumps(card, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def card_fingerprint(card: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_card_json(card).encode("utf-8")).hexdigest()


class AgentCardSnapshot(CatalogModel):
    instance_id: Identifier
    agent_name: Identifier
    endpoint: Identifier
    card: dict[str, Any]
    fingerprint: str

    @model_validator(mode="after")
    def fingerprint_covers_card(self):
        if self.fingerprint != card_fingerprint(self.card):
            raise ValueError("Card fingerprint does not match frozen content")
        return self

    def matches(self, card: dict[str, Any]) -> bool:
        return self.fingerprint == card_fingerprint(card)


def freeze_agent_card(
    instance_id: str, agent_name: str, endpoint: str, card: dict[str, Any]
) -> AgentCardSnapshot:
    return AgentCardSnapshot(
        instance_id=instance_id,
        agent_name=agent_name,
        endpoint=endpoint,
        card=card,
        fingerprint=card_fingerprint(card),
    )

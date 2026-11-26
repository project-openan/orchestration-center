# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Frozen role bindings, including mixed templates. Hashes are not authentication."""

import json
from typing import Literal

from pydantic import Field, model_validator

from host_agent.role_contract import RoleBinding, RoleSnapshot, content_digest

from orchestrate.core.model.card_snapshot import AgentCardSnapshot
from orchestrate.core.model.instance_binding import ResolutionContext, ResolutionPolicy
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import CatalogModel, Identifier


FrozenBinding = RoleBinding


class RoleExecutionSnapshot(CatalogModel):
    schema_version: Literal["role-pilot-v2"] = "role-pilot-v2"
    execution_id: Identifier
    catalog_version: Identifier
    # Content digest of the exact approved catalog release used for the
    # resolution, so a same-version catalog edit invalidates the arrangement.
    catalog_fingerprint: Identifier
    config_version: Identifier
    policy_version: Identifier
    context: ResolutionContext
    template: PSOP
    template_fingerprint: Identifier
    execution_psop: PSOP
    bindings: list[FrozenBinding] = Field(min_length=1)
    cards: list[AgentCardSnapshot] = Field(min_length=1)
    fingerprint: Identifier

    @model_validator(mode="after")
    def verify(self):
        # The wire invariants are shared with the Host; authoring retains its
        # richer PSOP/context types without maintaining a second rule engine.
        RoleSnapshot.model_validate(self.model_dump(mode="json"))
        return self


def freeze_role_execution(template: PSOP, result, cards: list[AgentCardSnapshot], execution_id: str,
                          *, catalog_fingerprint: str) -> RoleExecutionSnapshot:
    """Detach all input data and validate the entire envelope before returning."""
    fields = FrozenBinding.model_fields
    payload = dict(schema_version="role-pilot-v2", execution_id=execution_id,
        catalog_version=result.catalog_version, catalog_fingerprint=catalog_fingerprint,
        config_version=result.config_version,
        policy_version=result.policy_version, context=result.context.model_dump(mode="json"),
        template=template.model_dump(mode="json"),
        template_fingerprint=content_digest(template.model_dump(mode="json")),
        execution_psop=result.execution_psop.model_dump(mode="json"),
        bindings=[{k: record[k] for k in fields} for record in result.bindings],
        cards=[card.model_dump(mode="json") for card in cards])
    # JSON serialization creates an independent transport boundary.
    payload = json.loads(json.dumps(payload, allow_nan=False))
    payload["fingerprint"] = content_digest(payload)
    return RoleExecutionSnapshot.model_validate(payload)


def binding_metadata(snapshot: RoleExecutionSnapshot) -> dict:
    """Stable binding projection shared by dispatch and Host validation."""
    return RoleSnapshot.model_validate(snapshot.model_dump(mode="json")).binding_metadata()


def resolution_fingerprint(snapshot: RoleExecutionSnapshot, policy: ResolutionPolicy) -> str:
    """Confirmation digest over the frozen arrangement, excluding per-execution identity.

    Covers the template, resolved bindings, selected cards, trusted caller
    context (identity, scope, authorized set), the versions and the applied
    policy (tie-break and overrides). ``execution_id`` and the snapshot's own
    fingerprint (salted by that random id) are excluded, so re-reading an
    unchanged arrangement does not change the digest. This is an interactive
    consistency check only: not an authorization token, not anti-replay, and
    not business deduplication.
    """
    payload = snapshot.model_dump(mode="json")
    payload.pop("execution_id", None)
    payload.pop("fingerprint", None)
    context = payload.get("context")
    if isinstance(context, dict) and isinstance(context.get("authorized_instance_ids"), list):
        context["authorized_instance_ids"] = sorted(context["authorized_instance_ids"])
    return content_digest({
        "schema": "role-resolution-confirm-v1",
        "snapshot": payload,
        "policy": policy.model_dump(mode="json"),
    })

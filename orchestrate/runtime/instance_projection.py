# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Dispatch-time assembly for role resolution: trusted inputs in, frozen plan out.

This adapter turns live AgentCards and server.conf into resolver inputs. The
server authorization list is a deployment-wide ceiling, not a per-user ACL.
Candidate prerequisites: the registry endpoint must hit a declared HTTP+JSON
interface, every declared interface URL must be clean HTTP(S), and
authentication declarations must be structurally complete. It performs no
network probes.
"""

from typing import Literal, Optional
from dataclasses import dataclass
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, Field, PrivateAttr

from host_agent.role_contract import auth_declaration_complete, interface_url_admissible
from orchestrate.core.model.instance_binding import (
    InstanceRegistry, ObservedInstance, ResolutionContext, ResolutionPolicy,
    ServiceScope, load_instance_registry,
)
from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_execution_snapshot import RoleExecutionSnapshot
from orchestrate.runtime.role_admission import role_execution_admission
from orchestrate.runtime.role_resolver import ResolutionError


class ResolutionRequest(BaseModel):
    """Requested scope and instance subset; claimed caller_id is ignored."""

    scope: Optional[str] = Field(None, max_length=512)
    authorized_instance_ids: list[str] | None = None
    caller_id: Optional[str] = Field(None, max_length=256)
    _verified_caller_id: str | None = PrivateAttr(default=None)
    task_overrides: dict[str, str] = Field(default_factory=dict)
    group_overrides: dict[str, str] = Field(default_factory=dict)
    tie_break: Optional[Literal["error", "instance_id"]] = None
    # Confirmation digest from a preview; formal resolution refuses to
    # dispatch when the re-read arrangement no longer matches it.
    confirm_fingerprint: Optional[str] = Field(None, max_length=128)


def bind_resolution_identity(resolution: ResolutionRequest, request) -> ResolutionRequest:
    """Use middleware-authenticated identity, never the caller's claimed ID."""
    identity = getattr(request.state, "user_identity", None)
    machine = getattr(request.state, "machine_identity", None)
    resolution._verified_caller_id = (
        identity.username if identity is not None else
        f"machine:{machine.subject}" if machine is not None else "orchestration-center"
    )
    return resolution


def configured_registry_path() -> str | None:
    """server.conf key ``role_registry_path``; unset means no registry release."""
    from common.util.config_util import get_conf

    value = get_conf().get("role_registry_path")
    if value is None:
        return None
    return str(value).strip() or None


def configured_execution_scope() -> str | None:
    """server.conf key ``role_execution_scope`` as ``tenant/site/business_object``."""
    from common.util.config_util import get_conf

    value = get_conf().get("role_execution_scope")
    if value is None:
        return None
    return str(value).strip() or None


def configured_authorized_instances() -> list[str]:
    """server.conf key ``role_authorized_instances`` (comma-separated IDs)."""
    from common.util.config_util import get_conf

    value = get_conf().get("role_authorized_instances")
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def parse_scope(raw: str) -> ServiceScope:
    """Split ``tenant/site/business_object``; anything else is invalid input."""
    parts = [part.strip() for part in str(raw).split("/")]
    if len(parts) != 3 or not all(parts):
        raise ResolutionError(
            "RESOLUTION_INPUT_INVALID",
            f"execution scope must be tenant/site/business_object, got {raw!r}",
        )
    return ServiceScope(tenant=parts[0], site=parts[1], business_object=parts[2])


def build_context_and_policy(request: ResolutionRequest | None):
    """Constrain the requested subset to server authorization and bind identity."""
    request = request or ResolutionRequest()
    scope_raw = request.scope or configured_execution_scope()
    if not scope_raw:
        raise ResolutionError(
            "RESOLUTION_INPUT_INVALID",
            "execution scope required (request field scope or server.conf key "
            "role_execution_scope)",
        )
    authorized = set(configured_authorized_instances())
    if request.authorized_instance_ids is not None:
        requested = set(request.authorized_instance_ids)
        if requested - authorized:
            raise ResolutionError("RESOLUTION_INPUT_INVALID", "Requested instances exceed server authorization")
        authorized &= requested
    context = ResolutionContext(
        caller_id=request._verified_caller_id or "orchestration-center",
        scope=parse_scope(scope_raw),
        authorized_instance_ids=authorized,
    )
    policy = ResolutionPolicy(
        policy_version="policy-v1",
        tie_break=request.tie_break or "error",
        task_overrides=dict(request.task_overrides),
        group_overrides=dict(request.group_overrides),
    )
    return context, policy


def _declared_endpoints(card) -> list[str]:
    """Every endpoint the card declares: explicit ``url`` plus interface URLs."""
    endpoints = []
    url = str(getattr(card, "url", "") or "").strip()
    if url:
        endpoints.append(url)
    for interface in getattr(card, "supported_interfaces", None) or []:
        interface_url = str(getattr(interface, "url", "") or "").strip()
        if interface_url:
            endpoints.append(interface_url)
    return endpoints


def _cards_by_identity(agent_cards) -> dict:
    """Reject conflicting duplicate identities instead of choosing by input order.

    A card is registered under every declared endpoint, so a registry instance
    pinning any of them can observe it; two cards sharing one identity with
    different content are rejected.
    """
    cards_by_identity = {}
    for card in agent_cards or []:
        for endpoint in _declared_endpoints(card):
            identity = (str(getattr(card, "name", "") or ""), endpoint)
            if identity in cards_by_identity:
                if _card_payload(cards_by_identity[identity]) != _card_payload(card):
                    raise ResolutionError("INSTANCE_SNAPSHOT_MISMATCH", "Conflicting duplicate card identity")
                continue
            cards_by_identity[identity] = card
    return cards_by_identity


def _interfaces_admissible(payload: dict) -> bool:
    """Every declared interface URL is HTTP(S) with a host and no credentials."""
    interfaces = payload.get("supportedInterfaces")
    if not isinstance(interfaces, list) or not interfaces:
        return False
    return all(isinstance(interface, dict) and interface_url_admissible(interface.get("url"))
               for interface in interfaces)


def project_observations(
    registry: InstanceRegistry, agent_cards, cards_by_identity: dict | None = None,
) -> list[ObservedInstance]:
    """Project live cards to ObservedInstance; unmatched instances stay invisible.

    ``cards_by_identity`` may be supplied by a caller that already indexed
    and checked the cards (e.g. ``resolve_execution_plan``).
    """
    cards_by_identity = _cards_by_identity(agent_cards) if cards_by_identity is None else cards_by_identity
    observations = []
    for instance in registry.instances:
        card = cards_by_identity.get((instance.agent_name, instance.endpoint))
        if card is None:
            continue
        skills = {}
        for skill in (getattr(card, "skills", None) or []):
            skill_id = str(getattr(skill, "id", "") or getattr(skill, "name", "") or "").strip()
            if skill_id:
                skills[skill_id] = str(getattr(skill, "name", "") or skill_id).strip()
        payload = _card_payload(card)
        interfaces = payload.get("supportedInterfaces", [])
        prerequisites = (
            _interfaces_admissible(payload)
            and any(isinstance(interface, dict)
                    and interface.get("protocolBinding") == "HTTP+JSON"
                    and str(interface.get("url", "") or "") == instance.endpoint
                    for interface in interfaces)
            and auth_declaration_complete(payload)
        )
        observations.append(ObservedInstance(
            instance_id=instance.instance_id,
            agent_name=instance.agent_name,
            endpoint=instance.endpoint,
            skills=skills,
            prerequisites_passed=prerequisites,
        ))
    return observations


def _card_payload(card) -> dict:
    """Structured card dump: pydantic cards via aliases, proto cards via MessageToDict."""
    dump = getattr(card, "model_dump", None)
    if callable(dump):
        return dump(mode="json", by_alias=True, exclude_none=True)
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(card)


def resolve_execution_plan(
    psop: PSOP, request: ResolutionRequest | None, agent_cards,
) -> RoleExecutionSnapshot:
    """Resolve role tasks and freeze the execution envelope for dispatch.

    Raises:
        ResolutionError: invalid inputs, unconfigured/unloadable registry, or
            selection failures (e.g. RESOLUTION_INPUT_INVALID,
            INSTANCE_SNAPSHOT_MISMATCH).
        RoleReferenceError: the approved catalog release is unavailable
            (CATALOG_VERSION_UNAVAILABLE).
        ValueError: the frozen envelope fails snapshot validation.
    """
    from orchestrate.core.model.role_execution_snapshot import freeze_role_execution
    from orchestrate.runtime.role_resolver import resolve_role_bindings

    from orchestrate.core.catalog_gate import has_role_tasks

    if not has_role_tasks(psop):
        raise ResolutionError(
            "RESOLUTION_INPUT_INVALID",
            "resolve_execution_plan called for a workflow without role tasks",
        )
    # Deployment admission (REQ74 P4): one gate ahead of every center entry
    # (internal, external, by-id, by-intent), before any resolution work.
    admitted, reasons = role_execution_admission()
    if not admitted:
        raise ResolutionError(
            "ROLE_EXECUTION_NOT_ENABLED",
            "Role execution is not admitted on this deployment: " + ", ".join(reasons),
        )
    inputs = assemble_resolution_inputs(psop, request, agent_cards)
    result = resolve_role_bindings(
        psop, inputs.catalog, inputs.registry, inputs.observations, inputs.context, inputs.policy,
    )
    snapshot = freeze_resolution_snapshot(
        psop, result, inputs.cards_by_identity, uuid4().hex,
        catalog_fingerprint=inputs.catalog_fingerprint,
    )
    _verify_confirmation(snapshot, inputs.policy, request)
    return snapshot


def _verify_confirmation(snapshot, policy, request: ResolutionRequest | None) -> None:
    """Compare the freshly frozen arrangement with the previewed digest.

    The digest is a consistency check, not an authorization token: a mismatch
    means the workflow, catalog, scope, policy, chosen instances or cards
    changed after the caller confirmed, so the execution is refused with
    ``RESOLUTION_MISMATCH`` instead of silently dispatching other instances.
    On a match the returned snapshot is the exact frozen envelope that is
    dispatched -- it is never re-resolved.
    """
    if request is None or not request.confirm_fingerprint:
        return
    from orchestrate.core.model.role_execution_snapshot import resolution_fingerprint

    actual = resolution_fingerprint(snapshot, policy)
    if actual != request.confirm_fingerprint:
        raise ResolutionError(
            "RESOLUTION_MISMATCH",
            "The confirmed arrangement has changed; preview again before executing",
        )


@dataclass
class ResolutionInputs:
    """Trusted resolution inputs assembled once and shared by every path."""

    catalog: object
    registry: InstanceRegistry
    observations: list
    context: ResolutionContext
    policy: ResolutionPolicy
    cards_by_identity: dict
    catalog_fingerprint: str


def assemble_resolution_inputs(psop: PSOP, request: ResolutionRequest | None, agent_cards) -> ResolutionInputs:
    """Load catalog, registry, identity, authorization and live card projections.

    Shared by formal resolution and execution preview so both consume the
    same trusted inputs. Raises ``RoleReferenceError`` when the approved
    catalog release is unavailable and ``ResolutionError`` for invalid
    inputs or an unconfigured/unloadable registry.
    """
    from orchestrate.core.catalog_gate import (
        configured_catalog_path, load_approved_catalog,
    )

    catalog = load_approved_catalog(
        configured_catalog_path(), psop.catalog_version,
        subject=f"role workflow id={psop.id} catalog_version={psop.catalog_version}",
    )
    # Content digest of the exact release: a same-version catalog edit must
    # invalidate the arrangement (REQ74 P5 confirmation-digest guarantee).
    from orchestrate.core.model.role_execution_snapshot import content_digest

    catalog_fingerprint = content_digest(catalog.model_dump(mode="json"))
    registry_path = configured_registry_path()
    if not registry_path:
        logger.warning(
            "[RoleDispatch] Rejected role workflow id={}: no instance registry configured",
            psop.id,
        )
        raise ResolutionError(
            "RESOLUTION_INPUT_INVALID",
            "instance registry not configured (server.conf key role_registry_path)",
        )
    try:
        registry = load_instance_registry(registry_path)
    except (OSError, ValueError) as error:
        logger.warning(
            "[RoleDispatch] Instance registry {!r} cannot be loaded ({!r})",
            registry_path, error,
        )
        raise ResolutionError(
            "RESOLUTION_INPUT_INVALID", "instance registry cannot be loaded"
        ) from error
    context, policy = build_context_and_policy(request)
    cards_by_identity = _cards_by_identity(agent_cards)
    observations = project_observations(registry, agent_cards, cards_by_identity)
    return ResolutionInputs(
        catalog=catalog, registry=registry, observations=observations,
        context=context, policy=policy, cards_by_identity=cards_by_identity,
        catalog_fingerprint=catalog_fingerprint,
    )


def freeze_resolution_snapshot(template: PSOP, result, cards_by_identity: dict,
                               execution_id: str, *, catalog_fingerprint: str) -> RoleExecutionSnapshot:
    """Freeze selected full cards into the dispatch envelope."""
    from orchestrate.core.model.card_snapshot import freeze_agent_card
    from orchestrate.core.model.role_execution_snapshot import freeze_role_execution

    frozen_cards = []
    frozen_ids = set()
    for binding in result.bindings:
        if binding["instance_id"] in frozen_ids:
            continue
        frozen_ids.add(binding["instance_id"])
        card = cards_by_identity.get((binding["agent"], binding["endpoint"]))
        if card is None:
            raise ResolutionError(
                "INSTANCE_SNAPSHOT_MISMATCH",
                "selected instance card disappeared before freeze",
                task_ids=[binding["task_id"]],
            )
        frozen_cards.append(freeze_agent_card(
            binding["instance_id"], binding["agent"], binding["endpoint"],
            _card_payload(card),
        ))
    return freeze_role_execution(template, result, frozen_cards, execution_id,
                                 catalog_fingerprint=catalog_fingerprint)

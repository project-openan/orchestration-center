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
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Host dispatch adaptation for expanded role candidates.

Pins the SDK to the registry-selected interface, enforces the extension
four-check (on the first outbound content and on every negotiation
reply) and the authentication pre-check before dispatch, converts
dispatch failures into structured ``BusinessFailure`` errors, and
validates ``AuthProvider`` output at send time for the role tasks that
require authentication. Legacy instance tasks and auth-less role tasks
keep the provider's existing semantics; the SDK itself stays untouched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from typing import Any

from loguru import logger
from workflow_engine import BusinessFailure

from host_agent.dispatch_auth import DispatchValidationError
from host_agent.role_contract import RoleSnapshot

TASK_T_URI = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"
NEGOTIATION_T_URI = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Negotiation-T/v1"
# Task-T carries the business prompt; Negotiation-T is the SDK's native
# information-exchange round trip (negotiation agents answer a Task-T request
# with an INPUT_REQUIRED PROPOSE and expect a REPLY). Authorization-T and
# Notification-T activations stay outside the host support set.
SUPPORTED_EXTENSIONS = frozenset({TASK_T_URI, NEGOTIATION_T_URI})
ROLE_DISPATCH_FAILED = "ROLE_DISPATCH_FAILED"

_SAFE_MESSAGES = {
    "EXTENSION_UNKNOWN_ACTIVATED": "Activated extensions are not declared by the selected card",
    "EXTENSION_UNSUPPORTED": "Activated extensions are outside the supported extension set",
    "EXTENSION_NOT_ACTIVATED": "Required extensions are not activated",
    "EXTENSION_PAYLOAD_MISSING": "Required extension payload is missing",
    "AUTH_CREDENTIALS_MISSING": "No credentials or auth provider configured for the selected agent",
    "AUTH_METHOD_UNSUPPORTED": "Configured credentials or declared authentication headers are unsupported",
    "AUTH_PROVIDER_UNSATISFIED": "Auth provider did not produce a supported authentication header",
    "AUTH_HEADER_CONFLICT": "Auth provider produced conflicting authentication headers",
    "DISPATCH_FAILED": "Role dispatch failed",
}

# In-flight dispatch coordinates; the provider wrapper reads them at send time.
_dispatch_identity: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "role_dispatch_identity", default=None,
)


def project_dispatch_interfaces(snapshot: RoleSnapshot,
                                agent_cards: Sequence[Any]) -> list[Any]:
    """Return dispatch cards pinned to each selected instance endpoint.

    Selected cards keep only the HTTP+JSON interface matching the frozen
    endpoint, so the SDK's interface selection cannot drift to another
    declared endpoint. Unselected cards pass through untouched. The frozen
    snapshot, fingerprints and audit evidence keep every declared interface.
    """
    frozen_by_name = {card.agent_name: card for card in snapshot.cards}
    projected = []
    for agent_card in agent_cards:
        frozen = frozen_by_name.get(agent_card.name)
        if frozen is None:
            projected.append(agent_card)
            continue
        kept = [interface for interface in agent_card.supported_interfaces
                if interface.url == frozen.endpoint
                and interface.protocol_binding == "HTTP+JSON"]
        if not kept:
            affected = [binding for binding in snapshot.bindings
                        if binding.instance_id == frozen.instance_id]
            raise DispatchValidationError(
                "Selected endpoint is not a declared HTTP+JSON interface",
                reason="CARD_INTERFACE",
                task_ids=tuple(binding.task_id for binding in affected),
                instance_id=frozen.instance_id,
                role_ids=tuple(sorted({binding.role_id for binding in affected})),
            )
        if len(kept) == len(agent_card.supported_interfaces):
            projected.append(agent_card)
            continue
        pinned = type(agent_card)()
        pinned.CopyFrom(agent_card)
        del pinned.supported_interfaces[:]
        pinned.supported_interfaces.extend(kept)
        projected.append(pinned)
    return projected


def _declared_extensions(card: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    capabilities = card.get("capabilities")
    entries = capabilities.get("extensions") if isinstance(capabilities, dict) else None
    declared: set[str] = set()
    required: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        uri = entry.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            continue
        declared.add(uri)
        if entry.get("required"):
            required.add(uri)
    return declared, required


def _requires_authentication(card: Mapping[str, Any]) -> bool:
    # Mirrors the SDK trigger: schemes and requirements must both be present.
    return bool(card.get("securitySchemes") and card.get("securityRequirements"))


def _frozen_requirement_scheme_groups(card: Mapping[str, Any]) -> list[tuple[str, ...]]:
    """Scheme-name AND-groups of each declared requirement (dict cards)."""
    groups: list[tuple[str, ...]] = []
    for requirement in card.get("securityRequirements") or []:
        if isinstance(requirement, dict) and isinstance(requirement.get("schemes"), dict):
            group = tuple(str(name) for name in requirement["schemes"])
            if group:
                groups.append(group)
    return groups


def _frozen_group_header_names(card: Mapping[str, Any], group: tuple[str, ...],
                               entry: Mapping[str, Any]) -> list[str]:
    """Header names one requirement's schemes authenticate through (dict card).

    Mirrors the SDK's credentials interceptor: a configured ``auth_header``
    wins, an API key scheme writes its declared header, everything else
    writes the ``Authorization`` convention.
    """
    schemes = card.get("securitySchemes") or {}
    names: list[str] = []
    for scheme_name in group:
        scheme = schemes.get(scheme_name) or {}
        config = entry.get(scheme_name)
        config = config if isinstance(config, Mapping) else {}
        auth_header = config.get("auth_header")
        if isinstance(auth_header, str) and auth_header.strip():
            names.append(auth_header)
            continue
        api_key = scheme.get("apiKeySecurityScheme") or {}
        if str(api_key.get("location") or "").lower() == "header" and api_key.get("name"):
            names.append(str(api_key["name"]))
            continue
        names.append("Authorization")
    return names


def _scheme_config_complete(config: Any) -> bool:
    """Mirror the SDK login requirements; optional defaults never reject."""
    if not isinstance(config, dict) or not config.get("login_url"):
        return False
    request_fields = config.get("request_fields")
    if isinstance(request_fields, dict) and request_fields:
        return True
    return bool(config.get("username") and config.get("password"))


def _credentials_lookup(
    credentials_config: str | Mapping[str, Any] | None,
) -> Callable[[str], Any]:
    """Resolve credentials exactly like the SDK's transport does."""
    if credentials_config is None:
        return lambda agent_name: None
    from workflow_engine.client.credential_service import AgentAuthManager

    if isinstance(credentials_config, str):
        manager = AgentAuthManager(config_path=credentials_config)
    else:
        manager = AgentAuthManager(config=dict(credentials_config))
    return manager.get_config


def _scheme_header_contract(scheme: Any,
                            config: Mapping[str, Any]) -> tuple[str, str]:
    """Exact header spelling and value kind one scheme authenticates with.

    Mirrors the SDK's credentials interceptor: a configured
    ``auth_header`` wins (its ``auth_header_prefix`` shapes the value, so
    only non-emptiness is enforced), an API key scheme writes its declared
    header name, everything else writes the ``Authorization`` bearer
    convention.
    """
    auth_header = config.get("auth_header")
    if isinstance(auth_header, str) and auth_header.strip():
        return auth_header, "raw"
    if scheme is not None and scheme.HasField("api_key_security_scheme"):
        api_key = scheme.api_key_security_scheme
        if str(api_key.location or "").lower() == "header" and api_key.name:
            return str(api_key.name), "raw"
    return "Authorization", "bearer"


def _effective_auth_headers(
    agent_card: Any, credentials_entry: Any,
) -> tuple[dict[str, str], list[tuple[tuple[str, str], ...]]]:
    """Effective auth header names and requirement contracts of a card.

    Returns the lowercase-to-exact spelling map for canonicalizing
    provider output and the per-requirement ``(header, kind)`` AND-groups
    for validating it. The validation groups keep the alternative
    semantics (any one requirement, every scheme's header). The spelling
    map mirrors the SDK's credentials interceptor: it adopts the first
    requirement whose every scheme carries a usable credentials
    configuration and writes that group's headers (a configured
    ``auth_header`` wins, then the declared API key name, then the
    ``Authorization`` convention). Schemes in incomplete, skipped groups
    contribute nothing, so the provider output always aligns with the
    headers the credentials side actually writes. Without an adoptable
    requirement the declared spellings apply, keeping the provider's own
    output internally consistent.
    """
    schemes = getattr(agent_card, "security_schemes", None) or {}
    entry = credentials_entry if isinstance(credentials_entry, Mapping) else {}
    declared: dict[str, str] = {}
    adopted: list[str] | None = None
    contracts: list[tuple[tuple[str, str], ...]] = []
    for requirement in getattr(agent_card, "security_requirements", None) or []:
        group: list[tuple[str, str]] = []
        group_headers: list[str] = []
        complete = True
        for scheme_name in getattr(requirement, "schemes", None) or ():
            config = entry.get(str(scheme_name))
            config = config if isinstance(config, Mapping) else {}
            header, kind = _scheme_header_contract(schemes.get(scheme_name), config)
            group.append((header.lower(), kind))
            declared.setdefault(header.lower(), header)
            if not _scheme_config_complete(config):
                complete = False
            else:
                group_headers.append(header)
        if group:
            contracts.append(tuple(group))
        if adopted is None and complete and group_headers:
            adopted = group_headers
    if adopted is not None:
        names: dict[str, str] = {}
        for header in adopted:
            names.setdefault(header.lower(), header)
        return names, contracts
    return dict(declared), contracts


def _header_value_satisfies(kind: str, value: Any) -> bool:
    """Non-empty value; bearer headers must carry the Bearer token format."""
    if not isinstance(value, str) or not value.strip():
        return False
    if kind != "bearer":
        return True
    scheme, _, token = value.strip().partition(" ")
    return scheme.lower() == "bearer" and bool(token.strip())


class ValidatingAuthProvider:
    """Wrap an injected provider; verify auth headers on validated sends.

    Validation and exception conversion apply only while a role task that
    requires authentication is in flight, tracked through the dispatch
    identity context variable; every other caller (legacy instance tasks,
    auth-less role tasks) keeps the provider's existing semantics. Within
    a validated send the wrapper delegates to the inner provider, applies
    case-insensitive merge semantics to the output, and then requires it
    to satisfy the card's authentication requirements as they are actually
    configured: the effective header spellings mirror the first fully
    configured requirement the credentials side adopts (a configured
    ``auth_header`` wins, then the declared API key name, then the
    ``Authorization`` convention); schemes in skipped, incomplete groups
    contribute nothing, and without an adoptable requirement the declared
    spellings apply. Every scheme of one requirement
    with non-empty, correctly formatted headers, one of the alternative
    requirements, or a host-configured custom-header convention passes.
    Empty output, a wrong format, a case conflict, or an exception fails
    closed before the request leaves the process. The provider is never
    called an extra time.
    """

    def __init__(self, inner: Any, *, execution_id: str = "",
                 custom_headers: Sequence[str] = (),
                 credentials: str | Mapping[str, Any] | None = None):
        self._inner = inner
        self._execution_id = execution_id
        self._custom_headers = frozenset(custom_headers)
        self._credentials = _credentials_lookup(credentials)

    def apply_auth(self, agent_name: str, agent_card: Any,
                   headers: dict[str, str]) -> None:
        identity = _dispatch_identity.get()
        if identity is None or identity.get("agent") != agent_name:
            self._inner.apply_auth(agent_name, agent_card, headers)
            return
        before = dict(headers)
        try:
            self._inner.apply_auth(agent_name, agent_card, headers)
        except BusinessFailure:
            raise
        except Exception as exc:
            raise self._unsatisfied(agent_name, error_type=type(exc).__name__) from exc
        names, contracts = _effective_auth_headers(agent_card,
                                                   self._credentials(agent_name))
        self._merge_provider_headers(before, headers, names, agent_name)
        if self._custom_convention_satisfied(headers):
            return
        lowered = {str(name).lower(): value for name, value in headers.items()}
        for group in contracts:
            if all(_header_value_satisfies(kind, lowered.get(header))
                   for header, kind in group):
                return
        raise self._unsatisfied(agent_name)

    def _merge_provider_headers(self, before: Mapping[str, str],
                                headers: dict[str, str],
                                canonical: Mapping[str, str],
                                agent_name: str) -> None:
        """Case-insensitive merge semantics for the provider's output.

        The SDK's interceptor merges provider headers into the request by
        exact dictionary key, so a case variant of an authentication
        header would bypass its conflict convention and put two headers
        with the same name on the wire. Within the provider's output (and
        against headers already present), case-insensitive duplicates with
        equal values collapse into one entry and different values are
        rejected. Headers matching the effective authentication names are
        rewritten to the spelling the credentials side writes, so equal
        values dedupe and conflicting values trip the SDK's own conflict
        rejection where the provider's output meets the credentials-backed
        headers.
        """
        prior_values = {str(name).lower(): value for name, value in before.items()}
        for name, value in list(headers.items()):
            lowered = str(name).lower()
            prior = prior_values.get(lowered)
            if prior is not None and prior != value:
                raise self._header_conflict(agent_name, lowered)
            prior_values[lowered] = value
        merged: dict[str, str] = {}
        spelling: dict[str, str] = {}
        for name, value in headers.items():
            lowered = str(name).lower()
            target = canonical.get(lowered) or spelling.setdefault(lowered, name)
            merged[target] = value
        headers.clear()
        headers.update(merged)

    def _custom_convention_satisfied(self, headers: Mapping[str, str]) -> bool:
        if not self._custom_headers:
            return False
        wanted = {str(name).lower() for name in self._custom_headers}
        return any(str(name).lower() in wanted
                   and isinstance(value, str) and value.strip()
                   for name, value in headers.items())

    def _failure_details(self, reason: str) -> dict[str, Any]:
        details: dict[str, Any] = {"reason": reason}
        identity = _dispatch_identity.get()
        if identity is not None:
            details["execution_id"] = identity.get("execution_id") or self._execution_id
            if identity.get("task_id") is not None:
                details["task_id"] = identity["task_id"]
            if identity.get("instance_id") is not None:
                details["instance_id"] = identity["instance_id"]
        elif self._execution_id:
            details["execution_id"] = self._execution_id
        return details

    def _unsatisfied(self, agent_name: str, error_type: str | None = None) -> BusinessFailure:
        details = self._failure_details("AUTH_PROVIDER_UNSATISFIED")
        if error_type is not None:
            details["error_type"] = error_type
        logger.warning(
            "[RoleHost] auth provider rejected agent={} reason=AUTH_PROVIDER_UNSATISFIED",
            agent_name,
        )
        return BusinessFailure(
            ROLE_DISPATCH_FAILED,
            _SAFE_MESSAGES["AUTH_PROVIDER_UNSATISFIED"],
            details=details,
        )

    def _header_conflict(self, agent_name: str, header: str) -> BusinessFailure:
        details = self._failure_details("AUTH_HEADER_CONFLICT")
        details["header"] = header
        logger.warning(
            "[RoleHost] auth provider rejected agent={} reason=AUTH_HEADER_CONFLICT header={}",
            agent_name, header,
        )
        return BusinessFailure(
            ROLE_DISPATCH_FAILED,
            _SAFE_MESSAGES["AUTH_HEADER_CONFLICT"],
            details=details,
        )


class _NegotiationGuard:
    """Re-run the extension four-check on negotiation reply content.

    The SDK asks the control point for follow-up content whenever a task
    answers INPUT_REQUIRED; without this guard only the first outbound
    content would be checked. A reply outside the declared-and-supported
    envelope raises before the next request is sent, and the failure
    keeps the task identity and flows through the SDK's cancellation
    cleanup unchanged.
    """

    def __init__(self, inner: Any, checker: Callable[[Any], None]):
        self._inner = inner
        self._checker = checker

    async def on_negotiation(self, request: Any) -> Any:
        reply = await self._inner.on_negotiation(request)
        reply_content = getattr(reply, "content", None)
        if reply_content is not None:
            self._checker(reply_content)
        return reply

    def __getattr__(self, name: str) -> Any:
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


class RoleDispatchEngineClient:
    """Engine-client wrapper enforcing role dispatch policy.

    Role-bound tasks run the extension four-check and the authentication
    pre-check before dispatch, and dispatch failures surface as structured
    ``BusinessFailure`` errors. Mapped legacy instance tasks pass straight
    through, keeping their existing behavior; unknown callbacks report the
    execution identity only, never a guessed task or instance.
    """

    def __init__(self, inner: Any, role_context: Any, snapshot: RoleSnapshot, *,
                 credentials: str | Mapping[str, Any] | None = None,
                 auth_provider: Any | None = None):
        self._inner = inner
        self._context = role_context
        self._snapshot = snapshot
        self._frozen_cards = {card.instance_id: card for card in snapshot.cards}
        self._credentials = _credentials_lookup(credentials)
        self._auth_provider = auth_provider

    async def dispatch(self, request: Any, content: Any, callbacks: Any = None) -> Any:
        try:
            binding = self._context.binding_for(request)
        except LookupError:
            raise self._failure("DISPATCH_FAILED", None,
                                error_type="LookupError") from None
        if binding is None:
            return await self._inner.dispatch(request, content, callbacks)
        identity = {"execution_id": self._snapshot.execution_id,
                    "task_id": binding.task_id,
                    "instance_id": binding.instance_id,
                    "agent": request.agent_name}
        card = self._frozen_cards[binding.instance_id].card
        self._check_extensions(card, content, identity)
        self._check_authentication(request, card, identity)
        sink = callbacks
        if callbacks is not None:
            sink = _NegotiationGuard(
                callbacks,
                lambda reply_content: self._check_extensions(card, reply_content, identity),
            )
        token = None
        if _requires_authentication(card):
            # The provider wrapper validates only inside this window;
            # legacy and auth-less dispatches keep the provider's
            # existing semantics.
            token = _dispatch_identity.set(identity)
        try:
            return await self._inner.dispatch(request, content, sink)
        except asyncio.CancelledError:
            raise
        except BusinessFailure:
            raise
        except Exception as exc:
            raise self._failure("DISPATCH_FAILED", identity,
                                error_type=type(exc).__name__) from exc
        finally:
            if token is not None:
                _dispatch_identity.reset(token)

    def _check_extensions(self, card: Mapping[str, Any], content: Any,
                          identity: Mapping[str, Any]) -> None:
        activated = set(getattr(content, "extensions", None) or ())
        declared, required = _declared_extensions(card)
        if activated - declared:
            raise self._failure("EXTENSION_UNKNOWN_ACTIVATED", identity)
        if activated - SUPPORTED_EXTENSIONS:
            raise self._failure("EXTENSION_UNSUPPORTED", identity)
        if required - activated:
            raise self._failure("EXTENSION_NOT_ACTIVATED", identity)
        if required - SUPPORTED_EXTENSIONS:
            raise self._failure("EXTENSION_UNSUPPORTED", identity)
        if TASK_T_URI in activated:
            metadata = getattr(content, "metadata", None) or {}
            if not metadata.get(TASK_T_URI):
                raise self._failure("EXTENSION_PAYLOAD_MISSING", identity)

    def _check_authentication(self, request: Any, card: Mapping[str, Any],
                              identity: Mapping[str, Any]) -> None:
        if not _requires_authentication(card):
            return
        entry = self._credentials(request.agent_name)
        if not entry:
            if self._auth_provider is None:
                raise self._failure("AUTH_CREDENTIALS_MISSING", identity)
            return
        # Requirements are alternatives: one fully configured requirement
        # satisfies the card, mirroring the SDK's interceptor.
        for group in _frozen_requirement_scheme_groups(card):
            headers = _frozen_group_header_names(card, group, entry)
            if len({name.lower() for name in headers}) != len(headers):
                # The SDK resolves such a group only through runtime token
                # values, so the adopted requirement cannot be predicted;
                # the combination is rejected instead of guessed. Supporting
                # it would require case-insensitive handling at the actual
                # header merge, which lives inside the SDK.
                raise self._failure("AUTH_METHOD_UNSUPPORTED", identity)
            if all(_scheme_config_complete(entry.get(name)) for name in group):
                return
        raise self._failure("AUTH_METHOD_UNSUPPORTED", identity)

    def _failure(self, reason: str, identity: Mapping[str, Any] | None,
                 error_type: str | None = None) -> BusinessFailure:
        details: dict[str, Any] = {"reason": reason}
        if identity is not None:
            details["execution_id"] = identity["execution_id"]
            details["task_id"] = identity["task_id"]
            details["instance_id"] = identity["instance_id"]
        else:
            details["execution_id"] = self._snapshot.execution_id
        if error_type is not None:
            details["error_type"] = error_type
        logger.warning("[RoleHost] dispatch rejected execution_id={} reason={}",
                       details["execution_id"], reason)
        return BusinessFailure(ROLE_DISPATCH_FAILED, _SAFE_MESSAGES.get(
            reason, _SAFE_MESSAGES["DISPATCH_FAILED"]), details=details)

    # ------------------------------------------------------------------
    # Delegation: the SDK drives the execution through these members.
    # ------------------------------------------------------------------

    @property
    def callback_timeout_seconds(self) -> int:
        return self._inner.callback_timeout_seconds

    @property
    def agent_names(self) -> list[str]:
        return self._inner.agent_names

    def get_card(self, agent_name: str) -> Any:
        return self._inner.get_card(agent_name)

    def update_agent_cards(self, agent_cards: list[Any]) -> None:
        self._inner.update_agent_cards(agent_cards)

    def begin_execution(self, execution_id: str, control_point: Any,
                        event_callback: Any) -> None:
        return self._inner.begin_execution(execution_id, control_point, event_callback)

    def end_execution(self, execution_id: str) -> None:
        return self._inner.end_execution(execution_id)

    async def send_message(self, agent_name: str, content: Any) -> Any:
        return await self._inner.send_message(agent_name, content)

    async def close(self) -> None:
        await self._inner.close()

    def __getattr__(self, name: str) -> Any:
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)

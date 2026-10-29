# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Seventh batch unit A: the shared contract accepts expanded role candidates.

Multi-interface cards, complete authentication declarations and required
extensions must freeze and validate; only structural violations (endpoint
match, embedded interface credentials, incomplete auth declaration) reject.
"""

from copy import deepcopy

import pytest
from a2a.types import AgentCard
from google.protobuf.json_format import MessageToDict, ParseDict
from pydantic import ValidationError

from host_agent.dispatch_auth import DispatchValidationError
from orchestrate.core.model.card_snapshot import freeze_agent_card
from orchestrate.core.model.role_execution_snapshot import freeze_role_execution
from test_role_pilot_delivery import prepared


def _candidate(mutate):
    """Freeze a candidate envelope from the pilot fixture with a mutated card.

    The mutation is applied before the protobuf round trip so the frozen dict
    and a live registry card share one canonical form.
    """
    template, result, cards = prepared()
    frozen = cards[0]
    payload = deepcopy(frozen.card)
    mutate(payload)
    live = ParseDict(payload, AgentCard())
    canonical = MessageToDict(live)
    rebuilt = freeze_agent_card(frozen.instance_id, frozen.agent_name, frozen.endpoint, canonical)
    return freeze_role_execution(template, result, [rebuilt], "execution-candidates", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"), live


def _raw_candidate(mutate):
    """Freeze a mutated card dict without any protobuf round trip.

    Malformed structures (null requirements, non-map schemes) are rejected by
    ParseDict before the code under test runs, so contract-level rejection
    must be exercised on the raw dictionary.
    """
    template, result, cards = prepared()
    frozen = cards[0]
    payload = deepcopy(frozen.card)
    mutate(payload)
    rebuilt = freeze_agent_card(frozen.instance_id, frozen.agent_name, frozen.endpoint, payload)
    return freeze_role_execution(template, result, [rebuilt], "execution-candidates", catalog_fingerprint="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")


def _unwrap_reason(exc_info):
    for error in exc_info.value.errors(include_input=False, include_url=False):
        cause = error.get("ctx", {}).get("error")
        if isinstance(cause, DispatchValidationError):
            return cause.reason
    return None


def _add_extra_interfaces(card):
    card["supportedInterfaces"].append({"url": "http://127.0.0.1:18993", "protocolBinding": "GRPC"})
    card["supportedInterfaces"].append({"url": "http://127.0.0.1:18994", "protocolBinding": "HTTP+JSON"})


def _endpoint_on_additional_interface(card):
    card["supportedInterfaces"].insert(0, {"url": "http://127.0.0.1:18996", "protocolBinding": "HTTP+JSON"})


def _complete_auth_and_required_extension(card):
    card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
    card["capabilities"] = {"extensions": [{"uri": "urn:example", "required": True}]}


def _endpoint_hits_no_http_json(card):
    card["supportedInterfaces"][0]["protocolBinding"] = "GRPC"


def _credentials_on_extra_interface(card):
    card["supportedInterfaces"].append({"url": "http://user:secret@127.0.0.1:18997", "protocolBinding": "GRPC"})


def _requirements_without_schemes(card):
    card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]


def _undeclared_scheme_reference(card):
    card["securitySchemes"] = {"real": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": {"ghost": {"list": []}}}]


@pytest.mark.parametrize("mutate", [
    _add_extra_interfaces,
    _endpoint_on_additional_interface,
    _complete_auth_and_required_extension,
])
def test_contract_accepts_expanded_candidates(mutate):
    snapshot, live = _candidate(mutate)
    assert snapshot.cards[0].card["name"] == live.name


@pytest.mark.parametrize("mutate, reason", [
    (_endpoint_hits_no_http_json, "CARD_INTERFACE"),
    (_credentials_on_extra_interface, "CARD_INTERFACE"),
    (_requirements_without_schemes, "AUTH_DECLARATION_INCOMPLETE"),
    (_undeclared_scheme_reference, "AUTH_DECLARATION_INCOMPLETE"),
])
def test_contract_rejects_structural_violations(mutate, reason):
    with pytest.raises(ValidationError) as exc:
        _candidate(mutate)
    assert _unwrap_reason(exc) == reason


def _malformed_interface_url(card):
    card["supportedInterfaces"].append({"url": "http://[broken", "protocolBinding": "GRPC"})


def _null_requirement(card):
    # Declared schemes plus a malformed requirement: the vacuous-reference
    # path must not treat the null entry as an empty reference set.
    card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [None]


def _non_map_schemes(card):
    card["securitySchemes"] = {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}}
    card["securityRequirements"] = [{"schemes": True}]


@pytest.mark.parametrize("mutate, reason", [
    (_malformed_interface_url, "CARD_INTERFACE"),
    (_null_requirement, "AUTH_DECLARATION_INCOMPLETE"),
    (_non_map_schemes, "AUTH_DECLARATION_INCOMPLETE"),
])
def test_contract_rejects_malformed_structures_on_raw_dicts(mutate, reason):
    with pytest.raises(ValidationError) as exc:
        _raw_candidate(mutate)
    assert _unwrap_reason(exc) == reason

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for AgentCard loading and security declaration compatibility."""

import copy
import json
from pathlib import Path

import pytest

from orchestrate.agentcard_loader import AgentCardLoader, _normalize_agent_dict


def _sample_card():
    sample_file = (
        Path(__file__).resolve().parents[1]
        / "samples"
        / "agentcard"
        / "spn_agent_card_city1.json"
    )
    return json.loads(sample_file.read_text(encoding="utf-8"))[0]


def test_normalization_supports_flat_bearer_and_api_key_without_mutating_source():
    card = _sample_card()
    card["securitySchemes"] = {
        "bearerAuth": {
            "scheme": "Bearer",
            "bearerFormat": "JWT",
            "description": "access token",
        },
        "apiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Custom-Key",
        },
    }
    card["securityRequirements"] = [{"schemes": ["bearerAuth", "apiKeyAuth"]}]
    original = copy.deepcopy(card)

    normalized = _normalize_agent_dict(card)

    assert card == original
    assert normalized["securitySchemes"]["bearerAuth"] == {
        "httpAuthSecurityScheme": {
            "scheme": "Bearer",
            "bearerFormat": "JWT",
            "description": "access token",
        }
    }
    assert normalized["securitySchemes"]["apiKeyAuth"] == {
        "apiKeySecurityScheme": {
            "location": "header",
            "name": "X-Custom-Key",
        }
    }
    assert normalized["securityRequirements"] == [
        {"schemes": {"bearerAuth": {}, "apiKeyAuth": {}}}
    ]


def test_missing_security_requirements_are_derived_from_schemes():
    card = _sample_card()
    del card["securityRequirements"]

    normalized = _normalize_agent_dict(card)

    assert "securityRequirements" not in card
    assert normalized["securityRequirements"] == [
        {"schemes": {"bearerAuth": {}}}
    ]


def test_loader_preserves_raw_card_and_parses_normalized_security(tmp_path):
    card = _sample_card()
    card["securitySchemes"] = {"bearerAuth": {"scheme": "Bearer"}}
    card["securityRequirements"] = [{"schemes": ["bearerAuth"]}]
    (tmp_path / "card.json").write_text(
        json.dumps({"agents": [card]}), encoding="utf-8"
    )
    loader = AgentCardLoader(tmp_path)

    raw = loader.get_raw_agent_dicts()
    parsed = loader.get_all_agent_cards()

    assert raw == [card]
    assert raw[0]["securitySchemes"]["bearerAuth"] == {"scheme": "Bearer"}
    assert len(parsed) == 1
    assert parsed[0].name == card["name"]
    assert parsed[0].security_schemes["bearerAuth"].http_auth_security_scheme.scheme == "Bearer"
    assert "bearerAuth" in parsed[0].security_requirements[0].schemes


def test_loader_skips_invalid_file_and_keeps_valid_cards(tmp_path):
    (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "valid.json").write_text(
        json.dumps([_sample_card()]), encoding="utf-8"
    )

    cards = AgentCardLoader(tmp_path).get_all_agent_cards()

    assert [card.name for card in cards] == ["SPN Domain Agent City1"]


def test_loader_rejects_directory_without_agent_definitions(tmp_path):
    (tmp_path / "empty.yaml").write_text("agents: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No agent card definitions found"):
        AgentCardLoader(tmp_path).get_raw_agent_dicts()

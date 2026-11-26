# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import pytest
from pydantic import ValidationError

from orchestrate.core.model.card_snapshot import (
    AgentCardSnapshot, canonical_card_json, card_fingerprint, freeze_agent_card,
)


CARD = {
    "name": "RAN Energy Saving Agent",
    "description": "负责RAN能效优化的自主闭环运行",
    "skills": [{"id": "ran-es-intent-exploration", "name": "RAN ES Intent Exploration"}],
    "supportedInterfaces": [{"protocolBinding": "HTTP+JSON", "url": "http://127.0.0.1:8899"}],
}


def frozen() -> AgentCardSnapshot:
    return freeze_agent_card(
        instance_id="ran-es-citya",
        agent_name="RAN Energy Saving Agent",
        endpoint="http://127.0.0.1:8899",
        card=deepcopy_card(),
    )


def deepcopy_card() -> dict:
    import copy
    return copy.deepcopy(CARD)


def test_fingerprint_is_deterministic():
    assert card_fingerprint(CARD) == card_fingerprint(deepcopy_card())


def test_fingerprint_ignores_key_order():
    reordered = {
        "supportedInterfaces": CARD["supportedInterfaces"],
        "skills": CARD["skills"],
        "description": CARD["description"],
        "name": CARD["name"],
    }
    assert card_fingerprint(reordered) == card_fingerprint(CARD)
    assert canonical_card_json(reordered) == canonical_card_json(CARD)


def test_fingerprint_preserves_non_ascii():
    assert "负责" in canonical_card_json(CARD)
    assert card_fingerprint(CARD) == card_fingerprint(deepcopy_card())


def test_skill_drift_changes_fingerprint():
    drifted = deepcopy_card()
    drifted["skills"][0]["id"] = "ran-es-intent-exploration-cityb"
    assert card_fingerprint(drifted) != card_fingerprint(CARD)
    assert frozen().matches(drifted) is False


def test_extension_drift_changes_fingerprint():
    drifted = deepcopy_card()
    drifted.setdefault("capabilities", {})["extensions"] = [{"uri": "other"}]
    assert frozen().matches(drifted) is False


def test_tampered_fingerprint_rejected():
    snapshot = frozen()
    with pytest.raises(ValidationError, match="fingerprint"):
        AgentCardSnapshot.model_validate({**snapshot.model_dump(), "fingerprint": "bad"})


def test_json_roundtrip_revalidates_content():
    snapshot = frozen()
    restored = AgentCardSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot
    assert restored.matches(CARD)


def test_freeze_binds_instance_identity():
    snapshot = frozen()
    assert snapshot.instance_id == "ran-es-citya"
    assert snapshot.card["name"] == "RAN Energy Saving Agent"


def test_card_swap_detected_on_revalidation():
    snapshot = frozen()
    swapped = {**snapshot.model_dump(), "card": {**CARD, "name": "Other Agent"}}
    with pytest.raises(ValidationError, match="fingerprint"):
        AgentCardSnapshot.model_validate(swapped)

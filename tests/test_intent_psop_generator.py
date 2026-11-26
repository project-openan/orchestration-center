# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for orchestrate/core/intent_psop_generator.py.

Covers:
- _prepare_agent_cards_json: normal, empty, multiple agents
- generate_psop_from_intent: success, empty intent, empty agent_cards,
  LLM error, name fallback from intent
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from orchestrate.core.intent_psop_generator import IntentPsopGenerator, IntentWorkflowGeneratorError
from orchestrate.core.model.psop import PSOP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_llm_instance(monkeypatch):
    """IntentPsopGenerator.__init__ resolves a real LLM instance via
    common.llm.get_llm_instance(), which raises ValueError when no chat
    capability is configured (the case in CI). Stub it at the psop_generator
    module (where the constructor looks it up) so construction succeeds
    without LLM credentials; individual tests still override self._llm."""
    monkeypatch.setattr(
        "orchestrate.core.psop_generator.get_llm_instance",
        lambda: MagicMock(),
    )


def _make_agent_card(name="agent1", description="desc", skills=None):
    card = MagicMock()
    card.name = name
    card.description = description
    if skills is None:
        skill = MagicMock()
        skill.name = "skill1"
        skill.description = "A test skill"
        card.skills = [skill]
    else:
        card.skills = skills
    return card


def _make_psop_mock(name="GeneratedWF", spec=PSOP):
    """Create a MagicMock that passes isinstance(x, PSOP) and has .steps."""
    mock = MagicMock(spec=spec)
    mock.name = name
    mock.steps = []
    mock.user_intent = ""
    return mock


# ===========================================================================
# _prepare_agent_cards_json
# ===========================================================================

class TestPrepareAgentCardsJson:
    def test_normal(self):
        gen = IntentPsopGenerator()
        cards = [_make_agent_card("agent1", "desc1")]
        result = gen._prepare_agent_cards_json(cards)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["name"] == "agent1"
        assert data[0]["description"] == "desc1"
        assert len(data[0]["skills"]) == 1

    def test_multiple_agents(self):
        gen = IntentPsopGenerator()
        cards = [
            _make_agent_card("agent1", "desc1"),
            _make_agent_card("agent2", "desc2"),
        ]
        result = gen._prepare_agent_cards_json(cards)
        data = json.loads(result)
        assert len(data) == 2

    def test_empty_list(self):
        gen = IntentPsopGenerator()
        result = gen._prepare_agent_cards_json([])
        data = json.loads(result)
        assert data == []

    def test_agent_with_multiple_skills(self):
        gen = IntentPsopGenerator()
        skill1 = MagicMock()
        skill1.name = "skill1"
        skill1.description = "desc"
        skill2 = MagicMock()
        skill2.name = "skill2"
        skill2.description = "desc2"
        card = _make_agent_card("agent1", "desc1", skills=[skill1, skill2])
        result = gen._prepare_agent_cards_json([card])
        data = json.loads(result)
        assert len(data[0]["skills"]) == 2


# ===========================================================================
# generate_psop_from_intent
# ===========================================================================

class TestGeneratePsopFromIntent:
    def test_success(self):
        gen = IntentPsopGenerator()
        mock_psop = _make_psop_mock("GeneratedWF")
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt, \
             patch("orchestrate.core.intent_psop_generator.parse_llm_json_response") as mock_parse:
            mock_llm.ask_llm.return_value = (None, "response")
            mock_prompt.return_value = "prompt"
            mock_parse.return_value = mock_psop
            result = gen.generate_psop_from_intent("do something", [_make_agent_card()])
            assert result is mock_psop
            assert result.user_intent == "do something"
            assert mock_prompt.call_args.args[0] == "do something"
            assert mock_prompt.call_args.kwargs["input_heading"] == "User Intent"

    def test_empty_intent_raises(self):
        gen = IntentPsopGenerator()
        with pytest.raises(IntentWorkflowGeneratorError, match="User intent cannot be empty"):
            gen.generate_psop_from_intent("", [_make_agent_card()])

    def test_whitespace_intent_raises(self):
        gen = IntentPsopGenerator()
        with pytest.raises(IntentWorkflowGeneratorError, match="User intent cannot be empty"):
            gen.generate_psop_from_intent("   ", [_make_agent_card()])

    def test_empty_agent_cards_raises(self):
        gen = IntentPsopGenerator()
        with pytest.raises(IntentWorkflowGeneratorError, match="agent_cards cannot be empty"):
            gen.generate_psop_from_intent("test intent", [])

    def test_llm_error_raises(self):
        gen = IntentPsopGenerator()
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt:
            mock_llm.ask_llm.side_effect = RuntimeError("LLM down")
            mock_prompt.return_value = "prompt"
            with pytest.raises(IntentWorkflowGeneratorError, match="Failed to generate PSOP"):
                gen.generate_psop_from_intent("test", [_make_agent_card()])

    def test_name_from_workflow_name(self):
        gen = IntentPsopGenerator()
        mock_psop = _make_psop_mock("")
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt, \
             patch("orchestrate.core.intent_psop_generator.parse_llm_json_response") as mock_parse:
            mock_llm.ask_llm.return_value = (None, "response")
            mock_prompt.return_value = "prompt"
            mock_parse.return_value = mock_psop
            gen.generate_psop_from_intent("test", [_make_agent_card()], workflow_name="MyWF")
            assert mock_psop.name == "MyWF"

    def test_name_fallback_from_intent(self):
        gen = IntentPsopGenerator()
        mock_psop = _make_psop_mock("")
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt, \
             patch("orchestrate.core.intent_psop_generator.parse_llm_json_response") as mock_parse:
            mock_llm.ask_llm.return_value = (None, "response")
            mock_prompt.return_value = "prompt"
            mock_parse.return_value = mock_psop
            gen.generate_psop_from_intent("do a thing", [_make_agent_card()])
            assert "do a thing" in mock_psop.name

    def test_name_fallback_truncated(self):
        gen = IntentPsopGenerator()
        mock_psop = _make_psop_mock("")
        long_intent = "a" * 100
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt, \
             patch("orchestrate.core.intent_psop_generator.parse_llm_json_response") as mock_parse:
            mock_llm.ask_llm.return_value = (None, "response")
            mock_prompt.return_value = "prompt"
            mock_parse.return_value = mock_psop
            gen.generate_psop_from_intent(long_intent, [_make_agent_card()])
            assert "..." in mock_psop.name

    def test_non_psop_response_raises(self):
        gen = IntentPsopGenerator()
        with patch.object(gen, "_llm") as mock_llm, \
             patch("orchestrate.core.intent_psop_generator.build_psop_generation_prompt") as mock_prompt, \
             patch("orchestrate.core.intent_psop_generator.parse_llm_json_response") as mock_parse:
            mock_llm.ask_llm.return_value = (None, "response")
            mock_prompt.return_value = "prompt"
            mock_parse.return_value = {"not": "a PSOP"}
            with pytest.raises(IntentWorkflowGeneratorError, match="Expected PSOP"):
                gen.generate_psop_from_intent("test", [_make_agent_card()])

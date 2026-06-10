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

import pytest

from orchestrate.core.prompts import (
    get_preprocess_input_prompt,
    get_choose_skill_prompt,
    get_generate_psop_prompt,
    get_intent_to_psop_prompt,
    get_retrieve_psop_prompt
)


class TestPreprocessInputPrompt:
    def test_contains_markdown_content(self):
        prompt = get_preprocess_input_prompt("# Step 1\nDo analysis")
        assert "# Step 1" in prompt
        assert "Do analysis" in prompt

    def test_asks_for_task_list(self):
        prompt = get_preprocess_input_prompt("test")
        assert "JSON" in prompt

    def test_handles_empty_input(self):
        prompt = get_preprocess_input_prompt("")
        assert isinstance(prompt, str)


class TestChooseSkillPrompt:
    def test_contains_actions_and_agents(self):
        actions = '["action1", "action2"]'
        agents = '[{"name": "Agent1", "skills": [{"name": "skill1"}]}]'
        prompt = get_choose_skill_prompt(actions, agents)
        assert "action1" in prompt
        assert "Agent1" in prompt
        assert "skill1" in prompt

    def test_asks_for_dict_output(self):
        prompt = get_choose_skill_prompt("[]", "[]")
        assert "json" in prompt.lower()

    def test_handles_empty_lists(self):
        prompt = get_choose_skill_prompt("[]", "[]")
        assert isinstance(prompt, str)


class TestGeneratePsopPrompt:
    def test_contains_all_inputs(self):
        prompt = get_generate_psop_prompt(
            "# Test SOP", ["task1", "task2"],
            '{"type":"object"}'
        )
        assert "# Test SOP" in prompt
        assert "task1" in prompt
        assert "task2" in prompt
        assert '"type":"object"' in prompt

    def test_contains_psop_schema(self):
        prompt = get_generate_psop_prompt("# SOP", [], '{"properties":{"steps":{}}}')
        assert "steps" in prompt

    def test_asks_for_json_output(self):
        prompt = get_generate_psop_prompt("test", [], "{}")
        assert "json" in prompt.lower()


class TestIntentToPsopPrompt:
    def test_contains_user_intent(self):
        prompt = get_intent_to_psop_prompt(
            "save energy on RAN",
            '[{"name":"ES Agent"}]',
            '{"type":"object"}'
        )
        assert "save energy on RAN" in prompt

    def test_contains_agent_cards(self):
        prompt = get_intent_to_psop_prompt(
            "intent",
            '[{"name":"Agent1","skills":[]}]',
            "{}"
        )
        assert "Agent1" in prompt

    def test_rag_default_shows_none(self):
        prompt = get_intent_to_psop_prompt("intent", "[]", "{}")
        assert "none" in prompt.lower()

    def test_rag_parameter_passed_through(self):
        prompt = get_intent_to_psop_prompt("intent", "[]", "{}", rag="custom kg")
        assert "custom kg" in prompt

    def test_contains_cross_layer_rules(self):
        prompt = get_intent_to_psop_prompt("intent", "[]", "{}")
        assert "layer" in prompt.lower()
        assert "context_from" in prompt

    def test_handle_special_characters(self):
        prompt = get_intent_to_psop_prompt("test <>&\"' intent", "[]", "{}")
        assert "test <>&\"' intent" in prompt


class TestRetrievePsopPrompt:
    def test_contains_intent_and_psops(self):
        prompt = get_retrieve_psop_prompt(
            "find SPN fault workflows",
            '[{"id":"1","name":"SPN Diagnosis"}]'
        )
        assert "find SPN fault workflows" in prompt
        assert "SPN Diagnosis" in prompt

    def test_handles_empty_psop_list(self):
        prompt = get_retrieve_psop_prompt("test", "[]")
        assert isinstance(prompt, str)

    def test_asks_for_id_list(self):
        prompt = get_retrieve_psop_prompt("test", "[{}]")
        assert "json" in prompt.lower()

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
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrate.core.psop_generator import PsopGenerator, WorkflowGeneratorError
from orchestrate.core.model.psop import PSOP, Task, Step, StepType, TaskStatus

@pytest.fixture
def mock_llm():
    with patch('orchestrate.core.psop_generator.get_llm_instance') as mock_get:
        llm = MagicMock()
        mock_get.return_value = llm
        yield llm

@pytest.fixture
def generator(mock_llm):
    return PsopGenerator()

class TestParseJsonResponse:
    def test_code_block_parsed(self, generator):
        result = generator._parse_json_response('```json\n{"key": "val"}\n```')
        assert result == {"key": "val"}

    def test_last_code_block_used(self, generator):
        result = generator._parse_json_response(
            '```json\n[1,2]\n```\n```json\n[3,4]\n```'
        )
        assert result == [3, 4]

    def test_no_code_block_raises(self, generator):
        with pytest.raises(ValueError, match="No JSON code block found"):
            generator._parse_json_response("no json here")

    def test_empty_code_block_raises(self, generator):
        with pytest.raises(ValueError, match="Empty JSON content"):
            generator._parse_json_response("```json\n   \n```")

    def test_invalid_json_raises(self, generator):
        with pytest.raises(ValueError, match="Invalid JSON format"):
            generator._parse_json_response("```json\nnot valid json!!!\n```")

    def test_pydantic_model_validation(self, generator):
        data = {
            "description": "test",
            "agent": "TestAgent",
            "skill": "test_skill",
            "status": "pending"
        }
        content = f"```json\n{json.dumps(data)}\n```"
        result = generator._parse_json_response(content, Task)
        assert isinstance(result, Task)
        assert result.agent == "TestAgent"
        assert result.skill == "test_skill"

    def test_pydantic_model_missing_fields(self, generator):
        content = '```json\n{"agent": "OnlyAgent"}\n```'
        with pytest.raises(Exception):
            generator._parse_json_response(content, Task)

    def test_json_block_preserves_whitespace(self, generator):
        result = generator._parse_json_response('```json\n  {"a":  1}  \n```')
        assert result == {"a": 1}

class TestExtractTasksFromSteps:
    def test_happy_path(self, generator, mock_llm):
        mock_llm.ask_llm.return_value = ("req_id", '```json\n["task1", "task2"]\n```')
        tasks = generator.extract_tasks_from_steps("# Step 1\nDo something")
        assert tasks == ["task1", "task2"]

    def test_wraps_exception(self, generator, mock_llm):
        mock_llm.ask_llm.side_effect = ValueError("LLM failure")
        with pytest.raises(WorkflowGeneratorError, match="Failed to extract tasks"):
            generator.extract_tasks_from_steps("# Step 1")

    def test_non_list_response_raises(self, generator, mock_llm):
        mock_llm.ask_llm.return_value = ("req_id", '```json\n{"not": "a list"}\n```')
        with pytest.raises(WorkflowGeneratorError):
            generator.extract_tasks_from_steps("# Step 1")

class TestMatchActionsToSkills:
    def test_happy_path(self, generator, mock_llm):
        mock_llm.ask_llm.return_value = ("req_id", '```json\n{"task1": "skill1"}\n```')
        mock_skill = MagicMock()
        mock_skill.configure_mock(name="skill1", description="does things")
        mock_card = MagicMock()
        mock_card.configure_mock(name="Agent1", description="desc", skills=[mock_skill])
        result = generator.match_actions_to_skills(["task1"], [mock_card])
        assert result == {"task1": "skill1"}

    def test_non_dict_response_raises(self, generator, mock_llm):
        mock_llm.ask_llm.return_value = ("req_id", '```json\n["not a dict"]\n```')
        mock_card = MagicMock()
        mock_card.configure_mock(name="A", description="d", skills=[])
        with pytest.raises(WorkflowGeneratorError):
            generator.match_actions_to_skills(["task1"], [mock_card])

    def test_wraps_exception(self, generator, mock_llm):
        mock_llm.ask_llm.side_effect = RuntimeError("boom")
        mock_card = MagicMock()
        mock_card.configure_mock(name="A", description="d", skills=[])
        with pytest.raises(WorkflowGeneratorError):
            generator.match_actions_to_skills(["task1"], [mock_card])


def _card(name, skills):
    card = MagicMock()
    card.configure_mock(name=name, description="desc", skills=list(skills))
    return card


def _skill(name):
    skill = MagicMock()
    skill.configure_mock(name=name, description="skill desc")
    return skill


def _psop_structure_json(agent="Invented Actor"):
    return json.dumps({
        "name": "WF",
        "steps": [{
            "name": "step1",
            "type": "AllSuccess",
            "subtasks": [{
                "description": "Action A",
                "agent": agent,
                "skill": "Skill X",
            }],
            "next": [],
        }],
    })


class TestNormalizeSubtaskAgents:
    def test_rewrites_invented_agent_to_skill_owner(self, generator):
        task = Task(description="Action A", agent="Invented Actor", skill="Skill X")
        psop = PSOP(name="WF", steps=[Step(name="step1", subtasks=[task])])
        PsopGenerator._normalize_subtask_agents(psop, {"Skill X": "Owner Agent"})
        assert psop.steps[0].subtasks[0].agent == "Owner Agent"

    def test_keeps_matching_agent(self, generator):
        task = Task(description="Action A", agent="Owner Agent", skill="Skill X")
        psop = PSOP(name="WF", steps=[Step(name="step1", subtasks=[task])])
        PsopGenerator._normalize_subtask_agents(psop, {"Skill X": "Owner Agent"})
        assert psop.steps[0].subtasks[0].agent == "Owner Agent"

    def test_unknown_skill_left_untouched(self, generator):
        task = Task(description="Action A", agent="Some Agent", skill="Mystery Skill")
        psop = PSOP(name="WF", steps=[Step(name="step1", subtasks=[task])])
        PsopGenerator._normalize_subtask_agents(psop, {"Skill X": "Owner Agent"})
        assert psop.steps[0].subtasks[0].agent == "Some Agent"


class TestSkillFallbackRouting:
    def test_generic_support_does_not_silently_replace_missing_business_skill(self, generator, mock_llm):
        mock_llm.ask_llm.side_effect = [
            ('', '```json\n["IP diagnosis"]\n```'),
            ('', '```json\n{"IP diagnosis":"none"}\n```'),
        ]
        cards = [_card('Support', [_skill('General Orchestration Support')])]
        preflow = SimpleNamespace(steps_md='IP diagnosis', name='WF', id='pf-1')
        with pytest.raises(WorkflowGeneratorError, match='No matching agent'):
            generator.generate_psop_workflow(preflow, cards)

    def test_structure_builder_cannot_introduce_an_unknown_skill(self, generator, mock_llm):
        data = json.loads(_psop_structure_json())
        data['steps'][0]['subtasks'][0]['skill'] = 'Invented skill'
        mock_llm.ask_llm.side_effect = [
            ('', '```json\n["Action A"]\n```'),
            ('', '```json\n{"Action A":"Skill X"}\n```'),
            ('', '```json\n'+json.dumps(data)+'\n```'),
        ]
        with pytest.raises(WorkflowGeneratorError, match='unknown skill'):
            generator.generate_psop_workflow(SimpleNamespace(steps_md='Action A', name='WF', id='pf-1'),
                                             [_card('Owner', [_skill('Skill X')])])

    def test_none_action_falls_back_to_generic_skill(self, generator, mock_llm):
        generator = PsopGenerator(fallback_skill="General Orchestration Support")
        mock_llm.ask_llm.side_effect = [
            ("req_id", '```json\n["Action A", "Helper chore"]\n```'),
            ("req_id", '```json\n{"Action A": "Skill X", "Helper chore": "none"}\n```'),
            ("req_id", f'```json\n{_psop_structure_json()}\n```'),
        ]
        cards = [_card("Owner Agent", [_skill("Skill X"),
                                       _skill("General Orchestration Support")])]
        preflow = SimpleNamespace(steps_md="# Step 1\nAction A", name="WF", id="pf-1")
        psop = generator.generate_psop_workflow(preflow, cards)
        assert isinstance(psop, PSOP)
        # the structure-building LLM invented an agent; it must be normalized
        assert psop.steps[0].subtasks[0].agent == "Owner Agent"
        # the 'none' action was routed through the fallback skill in the prompt
        structure_prompt = mock_llm.ask_llm.call_args_list[2].args[0]
        assert "General Orchestration Support" in structure_prompt
        assert "Helper chore" in structure_prompt

    def test_none_action_without_fallback_raises(self, generator, mock_llm):
        mock_llm.ask_llm.side_effect = [
            ("req_id", '```json\n["Action A", "Helper chore"]\n```'),
            ("req_id", '```json\n{"Action A": "Skill X", "Helper chore": "none"}\n```'),
        ]
        cards = [_card("Owner Agent", [_skill("Skill X")])]
        preflow = SimpleNamespace(steps_md="# Step 1\nAction A", name="WF", id="pf-1")
        with pytest.raises(WorkflowGeneratorError, match="No matching agent found"):
            generator.generate_psop_workflow(preflow, cards)

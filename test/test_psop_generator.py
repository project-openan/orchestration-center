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
        with pytest.raises(json.JSONDecodeError):
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

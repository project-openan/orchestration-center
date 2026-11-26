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
import json
import pytest
from common.util.json_utils import parse_llm_json_response
from pydantic import BaseModel


class SimpleModel(BaseModel):
    name: str
    value: int


class TestParseLlmJsonResponse:

    def test_single_code_block_returns_dict(self):
        text = '```json\n{"key": "val"}\n```'
        result = parse_llm_json_response(text)
        assert result == {"key": "val"}

    def test_last_code_block_used_when_multiple(self):
        text = '```json\n[1,2]\n```\nSome text\n```json\n[3,4]\n```'
        result = parse_llm_json_response(text)
        assert result == [3, 4]

    def test_no_code_block_raises_value_error(self):
        with pytest.raises(ValueError, match="No JSON code block found"):
            parse_llm_json_response("no json here")

    def test_empty_code_block_raises_value_error(self):
        with pytest.raises(ValueError, match="Empty JSON content"):
            parse_llm_json_response("```json\n   \n```")

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid JSON format"):
            parse_llm_json_response("```json\nnot valid json!!!\n```")

    def test_pydantic_model_validation_success(self):
        data = {"name": "test", "value": 42}
        content = f"```json\n{json.dumps(data)}\n```"
        result = parse_llm_json_response(content, SimpleModel)
        assert isinstance(result, SimpleModel)
        assert result.name == "test"
        assert result.value == 42

    def test_pydantic_model_missing_fields_raises(self):
        content = '```json\n{"name": "only_name"}\n```'
        with pytest.raises(Exception):
            parse_llm_json_response(content, SimpleModel)

    def test_preserves_whitespace_in_json(self):
        result = parse_llm_json_response('```json\n  {"a":  1}  \n```')
        assert result == {"a": 1}

    def test_nested_json_structure(self):
        data = {"outer": {"inner": [1, 2, 3]}}
        content = f"```json\n{json.dumps(data)}\n```"
        result = parse_llm_json_response(content)
        assert result == data

    def test_response_preview_in_no_block_error(self):
        long_text = "A" * 300
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json_response(long_text)
        # Preview should be truncated to 200 chars
        assert "A" in str(exc_info.value)

    def test_list_json_response(self):
        content = '```json\n["task1", "task2", "task3"]\n```'
        result = parse_llm_json_response(content)
        assert result == ["task1", "task2", "task3"]
        assert isinstance(result, list)

    def test_dict_json_response(self):
        content = '```json\n{"action1": "skill1", "action2": "skill2"}\n```'
        result = parse_llm_json_response(content)
        assert result == {"action1": "skill1", "action2": "skill2"}
        assert isinstance(result, dict)


def test_bare_json_without_code_fence_parses():
    assert parse_llm_json_response('{"name": "flow", "steps": []}') == {"name": "flow", "steps": []}


def test_json_with_leading_prose_and_trailing_text_parses():
    text = 'Here is the workflow you asked for:\n{"name": "flow"}\nLet me know if anything else is needed.'
    assert parse_llm_json_response(text) == {"name": "flow"}


def test_unbalanced_json_reports_possible_truncation():
    text = '{"name": "flow", "steps": [{"task_id": "'
    with pytest.raises(ValueError, match="truncation"):
        parse_llm_json_response(text)


def test_braces_inside_strings_do_not_confuse_the_span():
    text = 'prefix {"name": "a \\"quoted\\" {brace} case"} suffix'
    assert parse_llm_json_response(text) == {"name": 'a "quoted" {brace} case'}


@pytest.mark.parametrize("prefix,suffix", [("", ""), ("Matching results:\n", "\nDone")])
def test_array_of_objects_is_not_truncated_to_first_object(prefix, suffix):
    values = [{"action_id": "a1", "nested": {"text": "[quoted]"}}, {"action_id": "a2"}]
    assert parse_llm_json_response(prefix + json.dumps(values) + suffix) == values


def test_redacted_parse_error_keeps_response_out_of_logs_and_exceptions():
    from loguru import logger

    output = []
    sink = logger.add(lambda message: output.append(str(message)))
    try:
        with pytest.raises(ValueError) as error:
            parse_llm_json_response("private-model-response", redact_errors=True)
        assert "private-model-response" not in str(error.value)
        assert "private-model-response" not in "".join(output)
    finally:
        logger.remove(sink)

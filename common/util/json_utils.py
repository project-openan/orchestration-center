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

"""Shared JSON parsing utilities for extracting JSON from LLM code-block responses."""

import json
import re
from typing import Any, Dict, List, Optional, Type, Union

from loguru import logger
from pydantic import BaseModel



def _extract_json_span(text: str) -> Optional[str]:
    """Return the outermost balanced {...} or [...] span in *text*, or None.

    Honors string literals (braces inside quoted strings do not affect depth).
    Returns None when no opening brace/bracket exists, or when the span never
    closes -- the latter usually means the answer was cut off by an output
    token limit.
    """
    pairs = sorted((("{", "}"), ("[", "]")), key=lambda pair: text.find(pair[0]) if pair[0] in text else len(text))
    for opener, closer in pairs:
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        escaped = False
        for index in range(start, len(text)):
            ch = text[index]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        return None
    return None


def parse_llm_json_response(
    llm_response: str,
    output_model: Optional[Type[BaseModel]] = None,
    *,
    redact_errors: bool = False,
) -> Union[BaseModel, Dict[str, Any], List[Any]]:
    """Extract and parse JSON from LLM response code blocks.

    Finds the last ```json ... ``` block in *llm_response*, validates it,
    and optionally parses it into a Pydantic model.

    Args:
        llm_response: Raw LLM response string containing a JSON code block.
        output_model: Optional Pydantic model class to validate/parse into.

    Returns:
        Parsed JSON data as dict, list, or Pydantic model instance.

    Raises:
        ValueError: If no JSON block found, content is empty, or JSON is invalid.
    """
    matches = re.findall(r'```json(.*?)```', llm_response, re.DOTALL)
    json_str: Optional[str] = None
    if matches:
        json_str = matches[-1].strip()
    else:
        # Models do not always honor the ```json fence request: accept a bare
        # JSON object/array as well (leading/trailing prose is tolerated).
        try:
            # Prefer the complete JSON value: scanning for '{' first would
            # otherwise truncate an array of objects to its first element.
            json.loads(llm_response)
            json_str = llm_response
        except (json.JSONDecodeError, TypeError):
            json_str = _extract_json_span(llm_response)
        if json_str is None:
            preview = "[redacted]" if redact_errors else llm_response[:200]
            error_msg = (
                "No JSON code block found in LLM answer and no balanced JSON "
                "object/array detected (possible output truncation by the "
                f"model's max-token limit). Response preview: {preview}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
    if not json_str:
        preview = "[redacted]" if redact_errors else llm_response[:200]
        error_msg = f"Empty JSON content found in code block. Response preview: {preview}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        if output_model:
            return output_model.model_validate_json(json_str)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}")
        raise ValueError(f"Invalid JSON format: {e}") from e
    except Exception as e:
        logger.error("Failed to parse JSON into model: {}", type(e).__name__ if redact_errors else e)
        raise

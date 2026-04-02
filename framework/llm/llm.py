# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

"""
DeepSeek LLM Client Module

This module provides a client wrapper for interacting with DeepSeek's LLM API.
It handles API authentication, request formatting, and response parsing with
special support for reasoning models that provide chain-of-thought outputs.

Key Features:
- DeepSeek API integration with OpenAI-compatible client
- Separation of reasoning content and final answer
- Environment-based API key configuration
"""

import os
from typing import Tuple
from openai import OpenAI
from loguru import logger


class DeepSeekLLM:
    """Client for interacting with DeepSeek LLM API.

    This class encapsulates all interactions with DeepSeek's language models,
    providing a simplified interface for sending prompts and receiving responses.
    It automatically detects reasoning models and extracts chain-of-thought content.

    Attributes:
        _client: OpenAI-compatible client configured for DeepSeek API
        _model: Name of the DeepSeek model to use
    """

    def __init__(self, model: str = "deepseek-chat"):
        """Initialize DeepSeek LLM client.

        Args:
            model: Name of the DeepSeek model to use (default: "deepseek-chat")

        Raises:
            ValueError: If DEEPSEEK_API_KEY environment variable is not set
        """
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set")

        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self._model = model

    def ask_llm(self, prompt: str) -> Tuple[str, str]:
        """Send a prompt to the LLM and get the response.

        Args:
            prompt: The text prompt to send to the LLM

        Returns:
            Tuple containing (reasoning_content, final_answer)
            - reasoning_content: Chain-of-thought reasoning (empty for non-reasoning models)
            - final_answer: The final response from the LLM

        Raises:
            Exception: If LLM API call fails
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            message = response.choices[0].message

            if hasattr(message, 'reasoning_content'):
                reasoning = message.reasoning_content or ''
                content = message.content or ''
            else:
                reasoning = ''
                content = message.content or ''
            return reasoning, content

        except Exception as e:
            error_msg = f"LLM API调用失败: {str(e)}"
            logger.error(error_msg)
            logger.error(f"错误类型: {type(e).__name__}")
            raise Exception(f"LLM调用失败: {str(e)}")


def get_or_create_deepseek_llm_instance():
    """Factory function to get or create a DeepSeekLLM instance.

    Returns:
        A new DeepSeekLLM instance configured with default settings
    """
    return DeepSeekLLM()
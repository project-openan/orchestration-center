"""
LLM Module

This module provides a client wrapper for interacting with LLM API.
"""
from .llm import get_llm_instance
from .provider.llm_openai import OpenAIStyleLLM

__all__ = ["OpenAIStyleLLM", "get_llm_instance"]
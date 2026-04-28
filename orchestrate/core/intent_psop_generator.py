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
Intent PSOP Generator Module

This module provides the IntentPsopGenerator class for converting natural language user intents
directly into executable Parallel-Standard Operation Process (PSOP) workflows.

The generator uses LLM to:
1. Parse natural language user intent into structured business steps
2. Match tasks with available agent skills
3. Build PSOP structure based on task dependencies
4. Generate complete executable workflows in one step

Key components:
- IntentPsopGenerator: Main class for intent-based PSOP generation
- IntentWorkflowGeneratorError: Custom exception for intent workflow generation failures
"""

import json
from typing import List, Optional

from a2a.types import AgentCard
from loguru import logger

from orchestrate.core.model.psop import PSOP
from orchestrate.core.prompts import get_intent_to_psop_prompt
from orchestrate.core.psop_generator import PsopGenerator, WorkflowGeneratorError


class IntentWorkflowGeneratorError(Exception):
    """Custom exception for intent-based PSOP workflow generation failures.

    Raised when any step in the intent-to-PSOP generation process fails,
    including intent parsing, skill matching, or PSOP structure building.
    """
    pass


def get_plan_kg(user_intent: str):
    """Custom function to get planning knowledge from RAG"""
    return ""


class IntentPsopGenerator(PsopGenerator):
    """Main class for generating PSOP workflows directly from natural language intents.

    This class extends PsopGenerator to provide a one-step conversion from
    natural language user intents to executable PSOP workflows.

    Attributes:
        _llm: LLM instance for natural language processing tasks
    """

    def __init__(self):
        """Initialize the intent PSOP generator with an LLM instance."""
        super().__init__()

    def _prepare_agent_cards_json(self, agent_cards: List[AgentCard]) -> str:
        """Prepare AgentCards information in JSON format for LLM prompt.

        Args:
            agent_cards: List of available agents with their skills

        Returns:
            JSON string containing agent and skill information
        """
        agent_cards_list = [
            {
                'name': ac.name,
                'description': ac.description,
                'skills': [{"name":s.name, "description":s.description} for s in ac.skills]
            }
            for ac in agent_cards
        ]
        return json.dumps(agent_cards_list, ensure_ascii=False, indent=2)

    def generate_psop_from_intent(
            self,
            user_intent: str,
            agent_cards: List[AgentCard],
            workflow_name: Optional[str] = None
    ) -> PSOP:
        """Generate complete PSOP workflow directly from natural language intent.

        Main entry point for intent-based PSOP generation. This method performs
        a one-step conversion from natural language intent to executable PSOP.

        Args:
            user_intent: Natural language description of the business intent
            agent_cards: List of available agents with their skills
            workflow_name: Optional name for the generated workflow. If not provided,
                         a name will be generated from the intent.

        Returns:
            Complete PSOP workflow ready for execution

        Raises:
            IntentWorkflowGeneratorError: If any step in the generation process fails
        """
        if not user_intent or not user_intent.strip():
            raise IntentWorkflowGeneratorError("User intent cannot be empty")
        if not agent_cards:
            raise IntentWorkflowGeneratorError("agent_cards cannot be empty")

        try:
            # Prepare inputs for LLM
            agent_cards_json = self._prepare_agent_cards_json(agent_cards)
            psop_schema = json.dumps(PSOP.model_json_schema(), ensure_ascii=False, indent=2)

            # planning knowledge
            plan_kg = get_plan_kg(user_intent)

            # Generate PSOP using LLM
            prompt = get_intent_to_psop_prompt(user_intent, agent_cards_json, psop_schema, plan_kg)
            _, llm_res = self._llm.ask_llm(prompt)

            # Parse LLM response into PSOP object
            parsed_data = self._parse_json_response(llm_res, PSOP)

            # Type assertion for type checker
            if not isinstance(parsed_data, PSOP):
                raise IntentWorkflowGeneratorError(f"Expected PSOP object but got {type(parsed_data)}")

            psop_data: PSOP = parsed_data

            # Set workflow name if provided by user
            if workflow_name:
                psop_data.name = workflow_name

            if not psop_data.name or psop_data.name.strip() == "":
                intent_summary = user_intent[:50].strip()
                if len(user_intent) > 50:
                    intent_summary += "..."
                psop_data.name = f"Workflow: {intent_summary}"

            # Store original user intent
            psop_data.user_intent = user_intent

            logger.info(f"Successfully generated PSOP from intent: {psop_data.name}")
            logger.info(f"Generated {len(psop_data.steps)} steps from user intent")

            return psop_data

        except WorkflowGeneratorError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during intent-based PSOP generation: {e}")
            raise IntentWorkflowGeneratorError(f"Failed to generate PSOP from intent: {e}") from e

    def generate_psop_workflow_with_intent(
            self,
            user_intent: str,
            agent_cards: List[AgentCard],
            workflow_name: Optional[str] = None
    ) -> PSOP:
        """Alias for generate_psop_from_intent for consistency with parent class.

        This method provides the same interface as PsopGenerator.generate_psop_workflow
        but accepts natural language intent instead of PreFlow.

        Args:
            user_intent: Natural language description of the business intent
            agent_cards: List of available agents with their skills
            workflow_name: Optional name for the generated workflow

        Returns:
            Complete PSOP workflow ready for execution
        """
        return self.generate_psop_from_intent(user_intent, agent_cards, workflow_name)

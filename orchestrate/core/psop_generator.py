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
PSOP Generator Module

This module provides the PsopGenerator class for converting human-readable business processes
(PreFlow) into executable Parallel-Standard Operation Process (PSOP) workflows.

The generator uses LLM to:
1. Extract concrete tasks from markdown-formatted business steps
2. Match tasks with available agent skills
3. Build PSOP structure based on task dependencies
4. Generate complete executable workflows

Key components:
- PsopGenerator: Main class for PSOP generation
- WorkflowGeneratorError: Custom exception for workflow generation failures
"""

import json
from loguru import logger
import re
from typing import Type, Optional, Union, Any, Dict, List

from a2a.types import AgentCard
from pydantic import BaseModel

from common.llm import get_llm_instance
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.prompts import get_generate_psop_prompt, get_choose_skill_prompt, \
    get_preprocess_input_prompt


class WorkflowGeneratorError(Exception):
    """Custom exception for PSOP workflow generation failures.
    
    Raised when any step in the PSOP generation process fails,
    including task extraction, skill matching, or PSOP structure building.
    """
    pass


class PsopGenerator:
    """Main class for generating PSOP workflows from PreFlow inputs.
    
    This class orchestrates the complete PSOP generation process:
    1. Task extraction from markdown business steps
    2. Skill matching for extracted tasks
    3. PSOP structure building based on task dependencies
    4. Complete workflow generation
    
    Attributes:
        _llm: LLM instance for natural language processing tasks
    """

    def __init__(self):
        """Initialize the PSOP generator with an LLM instance."""
        self._llm = get_llm_instance()

    @staticmethod
    def _parse_json_response(
            llm_response: str,
            output_model: Optional[Type[BaseModel]] = None
    ) -> Union[BaseModel, Dict[str, Any], List[Any]]:
        """Parse JSON response from LLM output.
        
        Extracts JSON from code blocks in LLM responses and validates/parses it.
        
        Args:
            llm_response: Raw LLM response string containing JSON code blocks
            output_model: Optional Pydantic model to validate and parse JSON into
            
        Returns:
            Parsed JSON data as dict, list, or Pydantic model instance
            
        Raises:
            ValueError: If no JSON code block found, empty content, or invalid JSON
            JSONDecodeError: If JSON parsing fails
        """
        matches = re.findall(r'```json(.*?)```', llm_response, re.DOTALL)
        if not matches:
            error_msg = "No JSON code block found in LLM answer"
            logger.error(error_msg)
            raise ValueError(error_msg)

        json_str = matches[-1].strip()
        if not json_str:
            error_msg = "Empty JSON content found in code block"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            if output_model:
                return output_model.model_validate_json(json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse JSON into model: {e}")
            raise

    def extract_tasks_from_steps(self, pre_wf_md: str) -> List[str]:
        """Extract concrete tasks from markdown-formatted business steps.
        
        Uses LLM to parse human-readable business process steps and extract
        actionable tasks for agent execution.
        
        Args:
            pre_wf_md: Markdown string containing business process steps
            
        Returns:
            List of extracted task descriptions
            
        Raises:
            WorkflowGeneratorError: If task extraction fails
        """
        try:
            prompt = get_preprocess_input_prompt(pre_wf_md)
            _, llm_res = self._llm.ask_llm(prompt)
            all_steps = self._parse_json_response(llm_res)

            if not isinstance(all_steps, list):
                raise ValueError(f"Expected list from LLM response, got {type(all_steps)}")
            logger.info(f"Successfully extracted {len(all_steps)} tasks: {all_steps}")
            return all_steps
        except Exception as e:
            raise WorkflowGeneratorError(f"Failed to extract tasks from steps: {e}") from e

    def match_actions_to_skills(
            self,
            actions: List[str],
            agents_card: List[AgentCard]
    ) -> Dict[str, Any]:
        """Match extracted tasks with available agent skills.
        
        Uses LLM to find the most appropriate skill for each task
        based on agent capabilities and skill descriptions.
        
        Args:
            actions: List of task descriptions to match
            agents_card: List of agent cards with their skills
            
        Returns:
            Dictionary mapping task descriptions to skill names
            
        Raises:
            WorkflowGeneratorError: If skill matching fails
        """
        try:
            actions_str = json.dumps(actions, ensure_ascii=False, indent=2)
            agent_cards_list = [
                {
                    'name': ac.name,
                    'description': ac.description,
                    'skills': [s.model_dump(include={"name", "description"}) for s in ac.skills]
                }
                for ac in agents_card
            ]
            agents_card_str = json.dumps(agent_cards_list, ensure_ascii=False, indent=2)
            prompt = get_choose_skill_prompt(actions_str, agents_card_str)
            _, llm_res = self._llm.ask_llm(prompt)
            action_skill_pairs = self._parse_json_response(llm_res)
            if not isinstance(action_skill_pairs, dict):
                raise ValueError(f"Expected dict from LLM response, got {type(action_skill_pairs)}")
            logger.info(f"Successfully matched actions to skills: {len(action_skill_pairs)} matches")
            logger.info(f"Matching results: {action_skill_pairs}")
            return action_skill_pairs
        except Exception as e:
            raise WorkflowGeneratorError(f"Failed to match actions to skills: {e}") from e

    def build_psop_structure(
            self,
            preflow: PreFlow,
            tasks: List[Dict[str, Any]]
    ) -> PSOP:
        """Build PSOP structure from matched tasks and their dependencies.
        
        Uses LLM to analyze task dependencies and create a structured
        PSOP workflow with proper step sequencing and conditions.
        
        Args:
            preflow: Original PreFlow containing business logic
            tasks: List of tasks with agent and skill assignments
            
        Returns:
            Validated PSOP object with complete workflow structure
            
        Raises:
            WorkflowGeneratorError: If PSOP structure building fails
        """
        try:
            if not tasks:
                raise ValueError("Tasks list cannot be empty")
            psop_schema = json.dumps(PSOP.model_json_schema(), ensure_ascii=False, indent=2)
            prompt = get_generate_psop_prompt(preflow.steps_md, tasks, psop_schema)
            _, llm_res = self._llm.ask_llm(prompt)

            psop_data = self._parse_json_response(llm_res, PSOP)

            if not getattr(psop_data, 'steps', None):
                raise ValueError("Generated PSOP has no steps")

            if not isinstance(psop_data, PSOP):
                raise ValueError("LLM returned non-PSOP object")
            logger.info("PSOP workflow structure generated successfully")
            logger.info(f"Generated PSOP object structure:\n{psop_data.model_dump_json(indent=2)}")
            return psop_data
        except Exception as e:
            raise WorkflowGeneratorError(f"PSOP workflow generation failed: {e}") from e

    def generate_psop_workflow(
            self,
            preflow: PreFlow,
            agent_cards: List[AgentCard]
    ) -> PSOP:
        """Generate complete PSOP workflow from PreFlow and agent cards.
        
        Main entry point for PSOP generation. Orchestrates the complete process:
        1. Task extraction from PreFlow steps
        2. Skill matching for extracted tasks
        3. PSOP structure building
        4. Workflow assembly and validation
        
        Args:
            preflow: PreFlow containing business process steps
            agent_cards: List of available agents with their skills
            
        Returns:
            Complete PSOP workflow ready for execution
            
        Raises:
            WorkflowGeneratorError: If any step in the generation process fails
        """
        if not preflow.steps_md or not preflow.steps_md.strip():
            raise WorkflowGeneratorError("Preflow steps_md cannot be empty")
        if not agent_cards:
            raise WorkflowGeneratorError("agent_cards cannot be empty")

        try:
            all_tasks = self.extract_tasks_from_steps(preflow.steps_md)
            if not all_tasks:
                raise WorkflowGeneratorError("No tasks extracted from preflow")
            action_skill_pair = self.match_actions_to_skills(all_tasks, agent_cards)
            skill_dict: Dict[str, str] = {
                skill.name: agent_card.name
                for agent_card in agent_cards
                for skill in agent_card.skills
                if skill.name
            }
            step_list = []
            for action, skill_name in action_skill_pair.items():
                if skill_name not in skill_dict:
                    logger.warning(f"Skill '{skill_name}' not found in any agent's skill list")
                    continue
                step_list.append({
                    'task': action,
                    'skill': skill_name,
                    'agent': skill_dict[skill_name]
                })
            if not step_list:
                raise WorkflowGeneratorError("No valid tasks generated from PSOP")

            psop: PSOP = self.build_psop_structure(preflow, step_list)
            psop.name = preflow.name
            psop.related_preflow = preflow.id

            return psop
        except WorkflowGeneratorError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during PSOP generation: {e}")
            raise WorkflowGeneratorError(f"Unexpected error: {e}") from e

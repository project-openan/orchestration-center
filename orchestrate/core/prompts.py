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

"""
PSOP (Parallel-Standard Operation Process) Generation Prompt Templates

This module contains prompt templates for generating PSOP workflows from
human-readable business processes. PSOP is a workflow format that enables
parallel execution of tasks with dependency management.

The prompts are used by LLM to:
1. Extract concrete tasks from markdown-formatted business steps
2. Match tasks with available agent skills
3. Build PSOP structure based on task dependencies
4. Generate complete executable workflows
"""

PSOP_EXAMPLE = """
{
    "name": "Server Outage Diagnosis and Recovery",
    "steps": [
        {
            "name": "step1",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "description": "Check power and environment status of affected servers",
                    "agent": "Fault Agent",
                    "skill": "check-server-power-env"
                },
                {
                    "description": "Check hardware and software error logs",
                    "agent": "Fault Agent",
                    "skill": "check-server-hw-sw-faults"
                }
            ],
            "next": [
                {
                    "step": "step2",
                    "condition": "No server-side issue found"
                },
                {
                    "step": "step3",
                    "condition": "Server-side root cause identified"
                }
            ]
        },
        {
            "name": "step2",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "description": "Query network element alarm information",
                    "agent": "Fault Agent",
                    "skill": "query-network-alarms"
                },
                {
                    "description": "Check for backbone fiber cable breaks",
                    "agent": "Fault Agent",
                    "skill": "check-fiber-breaks"
                }
            ],
            "next": [
                {
                    "step": "step3",
                    "condition": "Network anomaly detected"
                },
                {
                    "step": "step4",
                    "condition": "No network anomaly detected"
                }
            ]
        },
        {
            "name": "step3",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "description": "Handle network-side fault recovery",
                    "agent": "Fault Agent",
                    "skill": "fault-recovery"
                }
            ],
            "next": [
                {
                    "step": "end",
                    "condition": "Fault recovery completed"
                }
            ]
        },
        {
            "name": "step4",
            "type": "AllSuccess",
            "subtasks": [
                {
                    "description": "Handle application-layer fault recovery",
                    "agent": "Fault Agent",
                    "skill": "app-fault-recovery"
                }
            ],
            "next": [
                {
                    "step": "end",
                    "condition": "Fault recovery completed"
                }
            ]
        }
    ]
}
"""


def get_preprocess_input_prompt(pre_wd_md: str) -> str:
    return f"""Extract the task performed in each of the following process steps.

## Process Steps
{pre_wd_md}

## Output Rules
1. Output as a JSON list, wrapped in ```json``` markers.
2. Do NOT extract an end/termination step as a task.
3. Do NOT output anything other than the JSON list.

## Output Example
```json
["Fetch IP list of affected servers", "Check for power or environment faults on servers", "..."]
```
"""


def get_choose_skill_prompt(actions: str, agents_card: str) -> str:
    return f"""As a senior IT operations expert, match each action below with the most appropriate AgentSkill.
For each action, output the skill name that should be used.

## Agent Skill Catalog
{agents_card}

## Actions
{actions}

## Important
1. The number of selected skills must match the number of actions.
2. If no suitable skill exists for an action, use "none" as the skill name.

## Output Format
```json
{{
    "action1": "some-skill",
    "action2": "some-skill",
    "action3": "some-skill"
}}
```"""


def get_generate_psop_prompt(preflow: str, tasks: list, psop_scheme: str) -> str:
    return f"""
You are an IT operations expert. Based on the process steps provided by domain experts,
assign each step to a specialized Agent and identify dependencies between Agent tasks.
Output the result in our custom PSOP workflow format.

## Process Steps
{preflow}

## Agent Tasks
{tasks}

## PSOP Format Specification
{psop_scheme}

## Planning Rules
1. If tasks have no explicit dependency, place them in the same step for parallel execution.
2. Leave non-required PSOP fields empty; do not fabricate values.
3. The final step's "next" should unconditionally go to "end":
   ```"next":[{{"step":"end", "condition":""}}]```
4. Output only the PSOP JSON; do not include any other text.

## Condition Rules (Critical for correct workflow execution)
5. **Use `""` (empty string) for unconditional transitions**: If a step must always
   proceed to its next step (e.g. step2 → step3 without any branching), set condition
   to `""`. This allows the executor to skip LLM routing and proceed directly.
6. **Only write explicit conditions when genuine branching exists**: Conditions are
   ONLY needed when a step has multiple outgoing paths (e.g., step1 can go to step2 OR
   step3). In that case, write a short, concrete condition that describes which outcome
   triggers which path.
7. **Make conditions matchable against agent output keywords**: Use specific terms
   that are LIKELY to appear literally or semantically in the agent's response text.
   - BAD: `"Recovery attempted"` (too vague, agent won't use these exact words)
   - GOOD: `"RAN-side anomaly found"` (agent output will contain anomaly/diagnosis keywords)
   - GOOD: `"No network issue detected"` (agent output will contain "normal" / "no fault")
8. **When in doubt, prefer unconditional**: A sequential workflow without genuine
   branches should use `""` conditions throughout. Only introduce conditions when
   the business logic TRULY requires different paths based on agent findings.

## Cross-Layer Orchestration Rules (Important)
- If a step needs to synthesize, summarize, or analyze results from preceding steps,
  classify it as an aggregation layer step.
- Aggregation steps must set layer=1 (execution layer defaults to 0) and include
  a context_from list referencing all upstream steps whose output is needed.
- context_from example: ["step1","step2"] injects the outputs of step1 and step2
  into the current step's Agent context.
- **Recommended**: When branching paths exist (multiple steps can reach the aggregation
  step), use context_from: ["*"] to include ALL predecessors transitively
  (direct + indirect ancestors), avoiding omissions. Set context_from to null
  (auto-derive) to let the engine determine direct predecessors dynamically at runtime.
- If a step's Agent operates independently without needing other step results,
  do NOT set context_from.

## Example Output
```json
{PSOP_EXAMPLE}
```
"""


def get_intent_to_psop_prompt(user_intent: str, agent_cards_json: str, psop_schema: str, rag: str = "") -> str:
    return f"""As a senior IT operations expert, generate a PSOP (Parallel-Standard Operation Process) workflow
directly from the user's intent.

## User Intent
{user_intent}

## Available Agents and Skills
{agent_cards_json}

## Planning Knowledge
{"none" if not rag else rag}

## PSOP Format Specification
{psop_schema}

## Generation Rules
1. **Step Decomposition**: Decompose the user intent into concrete, executable steps.
2. **Skill Matching**: Select an appropriate Agent and Skill for each step.
   Ensure both the Agent and Skill exist in the available catalog.
3. **Dependency Analysis**: Analyze inter-step dependencies to determine
   parallel vs. sequential execution.
4. **Conditional Branching**: Define reasonable transition conditions for each step.
   - **CRITICAL**: Use "condition": "" (empty) for sequential transitions where the next
     step must always execute. Only write explicit conditions when a step has multiple
     outgoing paths that depend on the agent's findings.
   - **Make conditions matchable**: Write conditions using keywords likely to appear in
     the agent's output. A condition like "Recovery attempted" is too vague; use
     concrete phrases like "anomaly detected" or "fault found".
   - **Prefer unconditional over conditional**: Most workflows are sequential. Do NOT
     create artificial branching conditions when the business logic is linear.
5. **Naming Convention**: Use "step1", "step2", ... format. Default type is "AllSuccess".

## Cross-Layer Orchestration Rules (Important)
6. **Layer Classification**:
   - Execution layer (layer=0): Steps that independently perform analysis, data collection, inspection, etc.
   - Aggregation layer (layer=1+): Steps that synthesize, summarize, or compare results from previous steps.
7. **Context Passing**:
   - Aggregation steps must set context_from with the list of upstream step names they depend on.
   - context_from example: ["step1","step2"] injects step1 and step2 outputs into the current step's Agent context.
   - **Recommended**: When branching paths exist (multiple steps can reach the aggregation step),
     use context_from: ["*"] to include ALL predecessors transitively (direct + indirect ancestors).
     Use null to let the engine auto-derive direct predecessors at runtime.
   - Execution layer steps do NOT need context_from.
8. **Typical Patterns**: When the user intent includes terms like "summarize", "synthesize",
   "root cause analysis", "generate final recommendations", etc., the final step should
   be an aggregation layer step.

## Output Format
Output the complete PSOP JSON wrapped in ```json``` markers.

## Example 1: Standard Linear/Branching Workflow
User Intent: Diagnose a server outage across the data center.

Available Agents and Skills: [Fault Agent with various diagnostic skills]

Output:
```json
{{
    "name": "Server Outage Diagnosis and Recovery",
    "steps": [
        {{
            "name": "step1",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "Check power and environment status of affected servers",
                    "agent": "Fault Agent",
                    "skill": "check-server-power-env"
                }},
                {{
                    "description": "Check hardware and software error logs",
                    "agent": "Fault Agent",
                    "skill": "check-server-hw-sw-faults"
                }}
            ],
            "next": [
                {{
                    "step": "step2",
                    "condition": "No server-side issue found"
                }},
                {{
                    "step": "step3",
                    "condition": "Server-side root cause identified"
                }}
            ]
        }},
        {{
            "name": "step2",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "Query network element alarm information",
                    "agent": "Fault Agent",
                    "skill": "query-network-alarms"
                }},
                {{
                    "description": "Check for backbone fiber cable breaks",
                    "agent": "Fault Agent",
                    "skill": "check-fiber-breaks"
                }}
            ],
            "next": [
                {{
                    "step": "step3",
                    "condition": "Network anomaly detected"
                }},
                {{
                    "step": "step4",
                    "condition": "No network anomaly detected"
                }}
            ]
        }},
        {{
            "name": "step3",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "Handle network-side fault recovery",
                    "agent": "Fault Agent",
                    "skill": "fault-recovery"
                }}
            ],
            "next": [
                {{
                    "step": "end",
                    "condition": "Fault recovery completed"
                }}
            ]
        }},
        {{
            "name": "step4",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "Handle application-layer fault recovery",
                    "agent": "Fault Agent",
                    "skill": "app-fault-recovery"
                }}
            ],
            "next": [
                {{
                    "step": "end",
                    "condition": "Fault recovery completed"
                }}
            ]
        }}
    ]
}}
```

## Example 2: Cross-Layer Workflow with Aggregation
User Intent: Investigate server failure and produce a comprehensive fault analysis report.

Available Agents and Skills: [Diagnostic Agent, Network Agent, Analysis Agent]

Output:
```json
{{
    "name": "Server Fault Investigation and Analysis Report",
    "steps": [
        {{
            "name": "step1",
            "type": "AllSuccess",
            "layer": 0,
            "subtasks": [
                {{
                    "description": "Check server power, environment, and hardware/software status",
                    "agent": "Diagnostic Agent",
                    "skill": "fault-diagnosis"
                }}
            ],
            "next": [
                {{
                    "step": "step2",
                    "condition": ""
                }}
            ]
        }},
        {{
            "name": "step2",
            "type": "AllSuccess",
            "layer": 0,
            "subtasks": [
                {{
                    "description": "Query network element alarm information",
                    "agent": "Network Agent",
                    "skill": "query-alarms"
                }}
            ],
            "next": [
                {{
                    "step": "step3",
                    "condition": ""
                }}
            ]
        }},
        {{
            "name": "step3",
            "type": "AllSuccess",
            "layer": 1,
            "context_from": ["*"],
            "subtasks": [
                {{
                    "description": "Synthesize all investigation results, perform root cause analysis, and generate a remediation report",
                    "agent": "Analysis Agent",
                    "skill": "root-cause-analysis"
                }}
            ],
            "next": [
                {{
                    "step": "end",
                    "condition": ""
                }}
            ]
        }}
    ]
}}
```

## Important Notes
1. The final step's "next" must be: [{{"step": "end", "condition": ""}}]
2. Use professional IT operations terminology and rigorous logic.
3. Ensure the generated PSOP conforms to the format specification.
4. Output only the JSON; do not include any explanatory text.
5. Evaluate whether cross-layer orchestration is needed based on the user intent.
   If needed, the last step should be an aggregation step with appropriate context_from.
"""


def get_retrieve_psop_prompt(user_intent: str, psop_list: str, top_n: int = 1) -> str:
    return f"""As a senior IT operations expert, select the top {top_n} most suitable existing PSOP workflow(s)
for the given user intent, ordered by relevance.

## User Intent
{user_intent}

## Available PSOP Workflows
{psop_list}

## Selection Criteria
1. **Intent Match**: Evaluate how well each PSOP's name, description, user_intent, tags, and tasks align with the user intent.
2. **Functional Coverage**: Assess whether the PSOP's capabilities cover the user's requirements.
3. **Domain Relevance**: Consider the IT operations domain specialization match.
4. **Relevance Ordering**: Order results from most to least relevant.

## Output Format
Output a JSON array of matched PSOP names, wrapped in ```json``` markers.
If fewer than {top_n} PSOPs are relevant, include only the relevant ones.

## Output Example
```json
["Server Outage Diagnosis and Recovery", "Network Fault Analysis"]
```

## Important Notes
1. Output only the JSON array; do not include any explanatory text.
2. If no suitable PSOP is found, output an empty array: [].
3. Ensure each selected PSOP name matches the list exactly (character for character).
4. Return at most {top_n} name(s)."""

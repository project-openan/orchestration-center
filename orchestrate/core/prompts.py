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
    "name" : "基站批量掉站故障诊断与恢复",
    "steps":[
        {
            "name":"step1",
            "type":"AllSuccess",
            "subtasks"[
                {
                    "description":"检查退服基站的动力环境故障",
                    "agent":"MAE故障Agent",
                    "skill":"检查基站动力环境故障",
                },
                {
                    "description":"检查退服基站的软硬件故障",
                    "agent":"MAE故障Agent",
                    "skill":"检查基站软硬件故障",
                },
            ],
            "next":[
                {
                    "step:"step2",
                    "condition":"基站侧未发现明显问题"
                },
                {
                    "step:"step3",
                    "condition":"基站侧发现故障原因"
                }
            ]
        },
        {
            "name":"step2",
            "type":"AllSuccess",
            "subtasks"[
                {
                    "description":"查询传输网元告警信息",
                    "agent":"MAE故障Agent",
                    "skill":"查询传输网元告警",
                },
                {
                    "description":"检查传输侧是否存在光缆中断",
                    "agent":"MAE故障Agent",
                    "skill":"检查传输侧是否存在光缆中断",
                },
            ],
            "next":[
                {
                    "step:"step3",
                    "condition":"传输侧发现异常"
                },
                {
                    "step:"step4",
                    "condition":"传输侧未发现异常"
                }
            ]
        },
        {
            "name":"step3",
            "type":"AllSuccess",
            "subtasks"[
                {
                    "description":"传输侧处理故障",
                    "agent":"MAE故障Agent",
                    "skill":"故障处理",
                }
            ],
            "next":[
                {
                    "step:"end",
                    "condition":"故障处理完成"
                }
            ]
        },
        {
            "name":"step4",
            "type":"AllSuccess",
            "subtasks"[
                {
                    "description":"处理无线网络故障",
                    "agent":"MAE故障Agent",
                    "skill":"处理无线网络故障",
                }
            ],
            "next":[
                {
                    "step:"end",
                    "condition":"故障处理完成"
                }
            ]
        }
    ]
}
"""


def get_preprocess_input_prompt(pre_wd_md: str) -> str:
    return f"""提取下面人工处理步骤中，每一步执行的任务
## 处理步骤
{pre_wd_md}
## 输出规则
1、用一个json列表输出,用'''json'''包裹结果。
2、结束步骤不需要提取为一个任务。
3、不用输出其他内容。

## 输出示例
```json
["无线侧获取批量掉站基站IP列表","无线排查掉站基站是否存在动环故障",...]
```
"""


def get_choose_skill_prompt(actions: str, agents_card: str) -> str:
    return f"""作为一个资深的无线网络运维专家，请你为下面每一个动作匹配对应的AgentSkill，输出每一个动作对应要使用的技能名称。
## 智能体技能信息
{agents_card}

## 动作
{actions}

## 注意点
1、选择的技能的数量，与动作数量保持一致。
2、如果没有技能可以完成该动作，技能名称填“无”。

## 输出格式
```json
{{
    "动作1": "xxx技能",
    "动作2": "xxx技能",
    "动作3": "xxx技能",
}}
```"""


def get_generate_psop_prompt(preflow: str, tasks: list, psop_scheme: str) -> str:
    return f"""
你是一个电信网络运维专家，我根据专家提供的人工处理步骤，将每一步安排给专业Agent完成。
请按照人工处理步骤中的逻辑，帮我识别下Agent任务之间的依赖关系，并输出我们自定义的PSOP格式的工作流。

## 人工处理步骤
{preflow}

## Agent任务
{tasks}

## PSOP格式
{psop_scheme}

## 规划规则
1、如果任务间不存在明确的依赖，则这些任务可以放到一个step中并行执行。
2、PSOP中的非必填字段留空，不用进行推理。
3、最后一步的next属性，无条件走end，next属性值如下： "next":[{{"step":"end, "condition":""}}]
4、仅输出psop即可，不用输出其他内容。

## 示例输出
```json
{PSOP_EXAMPLE}
```
"""


def get_intent_to_psop_prompt(user_intent: str, agent_cards_json: str, psop_schema: str, rag: str = "") -> str:
    return f"""作为一个资深的电信网络运维专家，请根据用户意图直接生成PSOP（Parallel-Standard Operation Process）工作流。

## 用户意图
{user_intent}

## 可用Agent及技能
{agent_cards_json}

## 规划知识
{"无" if not rag else rag}

## PSOP格式要求
{psop_schema}

## 生成规则
1. **步骤分解**：将用户意图分解为具体的、可执行的步骤
2. **技能匹配**：为每个步骤选择合适的Agent和Skill，确保选择的Agent和Skill在可用列表中
3. **依赖分析**：分析步骤间的依赖关系，确定并行/串行执行逻辑
4. **条件跳转**：为每个步骤设置合理的跳转条件
5. **命名规范**：步骤名称使用"step1"、"step2"等格式，每个步骤的type默认为"AllSuccess"

## 输出格式
请直接输出完整的PSOP JSON，用```json```包裹。

## 示例
用户意图：诊断基站批量掉站故障

可用Agent及技能：[包含MAE故障Agent等]

输出：
```json
{{
    "name": "基站批量掉站故障诊断与恢复",
    "steps": [
        {{
            "name": "step1",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "检查退服基站的动力环境故障",
                    "agent": "MAE故障Agent",
                    "skill": "检查基站动力环境故障"
                }},
                {{
                    "description": "检查退服基站的软硬件故障",
                    "agent": "MAE故障Agent",
                    "skill": "检查基站软硬件故障"
                }}
            ],
            "next": [
                {{
                    "step": "step2",
                    "condition": "基站侧未发现明显问题"
                }},
                {{
                    "step": "step3",
                    "condition": "基站侧发现故障原因"
                }}
            ]
        }},
        {{
            "name": "step2",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "查询传输网元告警信息",
                    "agent": "MAE故障Agent",
                    "skill": "查询传输网元告警"
                }},
                {{
                    "description": "检查传输侧是否存在光缆中断",
                    "agent": "MAE故障Agent",
                    "skill": "检查传输侧是否存在光缆中断"
                }}
            ],
            "next": [
                {{
                    "step": "step3",
                    "condition": "传输侧发现异常"
                }},
                {{
                    "step": "step4",
                    "condition": "传输侧未发现异常"
                }}
            ]
        }},
        {{
            "name": "step3",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "传输侧处理故障",
                    "agent": "MAE故障Agent",
                    "skill": "故障处理"
                }}
            ],
            "next": [
                {{
                    "step": "end",
                    "condition": "故障处理完成"
                }}
            ]
        }},
        {{
            "name": "step4",
            "type": "AllSuccess",
            "subtasks": [
                {{
                    "description": "处理无线网络故障",
                    "agent": "MAE故障Agent",
                    "skill": "处理无线网络故障"
                }}
            ],
            "next": [
                {{
                    "step": "end",
                    "condition": "故障处理完成"
                }}
            ]
        }}
    ]
}}
```

## 注意事项
1. 最后一步的next属性设置为：[{{"step": "end", "condition": ""}}]
2. 保持电信运维的专业术语和逻辑严谨性
3. 确保生成的PSOP符合格式要求
4. 仅输出JSON，不要有其他解释性文字
"""


def get_retrieve_psop_prompt(user_intent: str, psop_list: str) -> str:
    return f"""作为一个资深的电信网络运维专家，请根据用户意图从现有的PSOP工作流中选择最合适的一个。

## 用户意图
{user_intent}

## 可用PSOP工作流列表
{psop_list}

## 选择规则
1. **意图匹配**：分析用户意图与每个PSOP的名称和描述的匹配程度
2. **功能覆盖**：评估PSOP的功能是否能够满足用户意图的需求
3. **专业领域**：考虑电信运维的专业领域匹配度
4. **最佳匹配**：选择最符合用户意图的PSOP工作流

## 输出格式
请直接输出最匹配的PSOP名称，用```json```包裹。

## 输出示例
```json
"基站批量掉站故障诊断与恢复"
```

## 注意事项
1. 只输出PSOP名称，不要有其他解释性文字
2. 如果找不到合适的PSOP，输出空字符串：""
3. 确保选择的PSOP名称与列表中的名称完全一致
"""

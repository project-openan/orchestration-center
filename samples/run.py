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

import asyncio
import time

from loguru import logger

from framework import AgentCardLib
from framework.orchestration.model.preflow import PreFlow
from framework.orchestration.psop_generator import PsopGenerator
from framework.runtime.exec_engine import DynamicWorkflowEngine
from samples.util import MOCK_ES_WORKFLOW

def get_pre_workflow():
    pre_md = MOCK_ES_WORKFLOW
    preflow = PreFlow(
        name=f'Workflow_Energy_Saving',
        description='Workflow for Energy Saving in Wireless Networks',
        steps_md=pre_md
    )
    logger.info(f"[STEP 1] 预工作流 (PreFlow) 构建完成，名称：{preflow.name}")
    return preflow


async def agent_communication_simulation():
    start_time = time.time()
    logger.info(">>> 启动 A2A 通信模拟任务 >>>")
    try:
        # 获取预工作流
        preflow = _get_and_validate_preflow()
        if not preflow:
            return
        # 获取Agent列表
        agent_cards = _load_agents_and_get_cards()
        if not agent_cards:
            logger.error("无法获取Agent列表，终止流程")
            return
        # 生成给工作流
        workflow = _generate_workflow(preflow, agent_cards)
        if not workflow:
            return
        # 执行工作流
        await _execute_workflow(workflow, agent_cards)
    except Exception as e:
        logger.critical(f"[ERROR] 任务运行过程中发生未捕获异常 : {e}")
        raise
    finally:
        _log_completion(start_time)


def _get_and_validate_preflow():
    preflow = get_pre_workflow()
    if not preflow.steps_md:
        logger.error("[STEP 2] 错误: PreFlow缺少必要的步骤描述，无法继续生成工作流。")
        return None
    return preflow


def _load_agents_and_get_cards():
    agent_lib = AgentCardLib()
    return agent_lib.get_all_agent_cards()

def _generate_workflow(preflow, agent_cards):
    logger.info("[STEP 3] 正在生成 PSOP 工作流...")
    generator = PsopGenerator()

    workflow = generator.generate_psop_workflow(preflow, agent_cards)
    logger.info(f"[STEP 3] 工作流生成完成，ID : {workflow.name}, 包含{len(workflow.steps)} 个步骤")

    for i, step in enumerate(workflow.steps, 1):
        logger.info(f"  Step {i}: {step.name} ({step.subtasks})")
    return workflow


async def _execute_workflow(workflow, agent_cards):
    logger.info("[STEP 4] 初始化 DynamicWorkflowEngine...")
    engine = DynamicWorkflowEngine(workflow, agent_cards)
    logger.info(f"[STEP 4] 开始执行工作流...")
    execution_start = time.time()

    try:
        history = await engine.run()
        _log_execution_results(history, execution_start)
    except Exception as e:
        logger.critical(f"[STEP 4] 工作流执行过程中发生严重错误 : {e}")
        raise


def _log_execution_results(history, start_time):
    duration = time.time() - start_time
    if not history:
        logger.warning("[STEP 4] 执行完成，但历史记录为空。")
        return
    logger.info(f"[STEP 4] 执行成功！耗时:{duration:.2f} 秒")
    logger.info(f"[STEP 4] 共产生 {len(history)} 条执行记录")

    logger.info("_" * 30)
    logger.info("执行记录摘要:")
    for idx, log_entry in enumerate(history):
        content = str(log_entry)
        if len(content) > 200:
            content = content[:200] + "..."
        logger.info(f"[LOG {idx}] {content}")
    logger.info("_" * 30)


def _log_completion(start_time):
    total_time = time.time() - start_time
    logger.info(f">>> 任务执行完毕 <<<")
    logger.info(f"总耗时: {total_time:.2f} 秒")


if __name__ == "__main__":
    try:
        asyncio.run(agent_communication_simulation())
    except KeyboardInterrupt:
        logger.info("用户手动中断了程序")
    except Exception as e:
        logger.error(f"程序因异常退出 ： {e}")

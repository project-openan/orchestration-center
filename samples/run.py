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
    logger.info(f"[STEP 1] PreFlow construction completed, name: {preflow.name}")
    return preflow


async def agent_communication_simulation():
    start_time = time.time()
    logger.info(">>> Starting A2A communication simulation task >>>")
    try:
        # Get pre-workflow
        preflow = _get_and_validate_preflow()
        if not preflow:
            return
        # Get agent list
        agent_cards = _load_agents_and_get_cards()
        if not agent_cards:
            logger.error("Unable to retrieve agent list, terminating the process")
            return
        # Generate workflow
        workflow = _generate_workflow(preflow, agent_cards)
        if not workflow:
            return
        # Execute workflow
        await _execute_workflow(workflow, agent_cards)
    except Exception as e:
        logger.critical(f"[ERROR] Uncaught exception occurred during task execution: {e}")
        raise
    finally:
        _log_completion(start_time)


def _get_and_validate_preflow():
    preflow = get_pre_workflow()
    if not preflow.steps_md:
        logger.error("[STEP 2] Error: PreFlow is missing the necessary step description, cannot proceed with workflow generation.")
        return None
    return preflow


def _load_agents_and_get_cards():
    agent_lib = AgentCardLib()
    return agent_lib.get_all_agent_cards()

def _generate_workflow(preflow, agent_cards):
    logger.info("[STEP 3] Generating PSOP workflow...")
    generator = PsopGenerator()

    workflow = generator.generate_psop_workflow(preflow, agent_cards)
    logger.info(f"[STEP 3] Workflow generation completed, ID: {workflow.name}, contains {len(workflow.steps)} steps")

    for i, step in enumerate(workflow.steps, 1):
        logger.info(f"  Step {i}: {step.name} ({step.subtasks})")
    return workflow


async def _execute_workflow(workflow, agent_cards):
    logger.info("[STEP 4] Initializing DynamicWorkflowEngine...")
    engine = DynamicWorkflowEngine(workflow, agent_cards)
    logger.info("[STEP 4] Starting workflow execution...")
    execution_start = time.time()

    try:
        history = await engine.run()
        _log_execution_results(history, execution_start)
    except Exception as e:
        logger.critical(f"[STEP 4] Critical error occurred during workflow execution: {e}")
        raise


def _log_execution_results(history, start_time):
    duration = time.time() - start_time
    if not history:
        logger.warning("[STEP 4] Execution completed, but history is empty.")
        return
    logger.info(f"[STEP 4] Execution successful! Time taken: {duration:.2f} seconds")
    logger.info(f"[STEP 4] Total execution records generated: {len(history)}")

    logger.info("_" * 30)
    logger.info("Execution Record Summary:")
    for idx, log_entry in enumerate(history):
        content = str(log_entry)
        if len(content) > 200:
            content = content[:200] + "..."
        logger.info(f"[LOG {idx}] {content}")
    logger.info("_" * 30)


def _log_completion(start_time):
    total_time = time.time() - start_time
    logger.info(f">>> Task execution completed <<<")
    logger.info(f"Total time taken: {total_time:.2f} seconds")


if __name__ == "__main__":
    try:
        asyncio.run(agent_communication_simulation())
    except KeyboardInterrupt:
        logger.info("User manually interrupted the program")
    except Exception as e:
        logger.error(f"Program exited due to exception: {e}")

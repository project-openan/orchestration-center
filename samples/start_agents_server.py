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

import asyncio
import json
from pathlib import Path

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_rest_routes, create_agent_card_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict
from loguru import logger
from typing import List
from urllib.parse import urlparse

from common.custom import HandlerRegistry, InterfaceType
from orchestrate.registry_client.client_factory import AgentRegistryClientFactory
from orchestrate import AgentCardLoader
from orchestrate.workflow_storage_instance import get_workflow_storage
from samples.agents.energy_saving_agent import EnergySavingAgentExecutor
from samples.agents.energy_saving_intent_agent import EnergySavingIntentAgentExecutor
from samples.agents.live_streaming_agent import LiveStreamingAgentExecutor
from samples.agents.assurance_agent import AssuranceAgentExecutor
from samples.agents.ran_agent import RanAgentExecutor
from samples.agents.dispatch_agent import DispatchAgentExecutor
from samples.agents.spn_agent_city1 import SpnCity1AgentExecutor
from samples.agents.spn_agent_city2 import SpnCity2AgentExecutor
from samples.agents.uncertainty_agent import UncertaintySimulationAgentExecutor
from common.a2at_config import ensure_env_file_exists


def _agent_card_to_dict(agent_card: AgentCard) -> dict:
    return MessageToDict(agent_card)


def _is_agent_card_changed(local_dict: dict, remote_dict: dict) -> bool:
    local_normalized = json.dumps(local_dict, sort_keys=True, ensure_ascii=False)
    remote_normalized = json.dumps(remote_dict, sort_keys=True, ensure_ascii=False)
    return local_normalized != remote_normalized


async def register_or_update_agent(factory, agent_card: AgentCard) -> dict:
    local_dict = _agent_card_to_dict(agent_card)
    name = agent_card.name
    org = agent_card.provider.organization if agent_card.provider else ""
    try:
        existing = await factory.get(name, org)
    except Exception as e:
        logger.warning(f"Query registry for {name} failed: {e}, falling back to register")
        try:
            return await factory.register(agent_card)
        except Exception as reg_err:
            logger.error(f"Register agent card {name} failed: {reg_err}")
            return None

    if existing is None:
        try:
            result = await factory.register(agent_card)
            logger.info(f"Registered new agent card: {name} (org={org})")
            return result
        except Exception as e:
            logger.error(f"Register agent card {name} failed: {e}")
            return None

    remote_agent_cards = existing.get("agentCards", [])
    if remote_agent_cards:
        remote_dict = remote_agent_cards[0]
        if _is_agent_card_changed(local_dict, remote_dict):
            try:
                result = await factory.update_full(name, org, agent_card)
                logger.info(f"Updated agent card: {name} (org={org}), content changed")
                return result
            except Exception as e:
                logger.error(f"Update agent card {name} failed: {e}")
                return None
        else:
            logger.info(f"Agent card {name} (org={org}) already registered, no changes detected, skipped")
            return existing
    else:
        try:
            result = await factory.register(agent_card)
            logger.info(f"Registered agent card: {name} (org={org})")
            return result
        except Exception as e:
            logger.error(f"Register agent card {name} failed: {e}")
            return None


def pre_insert_psop():
    from common.util.config_util import get_conf
    if get_conf().get("persistence_mode", "file").lower() == "file":
        logger.info("Persistence mode is file, skipping pre_insert_psop")
        return

    ensure_env_file_exists()
    logger.info("A2AT SDK environment file initialized")
    
    storage = get_workflow_storage()
    for wf_id in storage.list_psops():
        psop = storage.load_psop(wf_id)
        if psop is None:
            logger.warning(f"pre_insert_psop: workflow {wf_id} not found, skipping")
            continue
        save_handle = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        save_handle.handle(psop)


async def start_server(agent_card: AgentCard, port: int, host: str = "127.0.0.1") -> None:
    agent2class = {
        "RAN Energy Saving Agent": EnergySavingAgentExecutor,
        "Energy Saving Intent Agent": EnergySavingIntentAgentExecutor,
        "Live Streaming Agent": LiveStreamingAgentExecutor,
        "Assurance Agent": AssuranceAgentExecutor,
        "RAN Agent": RanAgentExecutor,
        "Transport Workbench Agent": DispatchAgentExecutor,
        "SPN Fault Handling Agent City1 OMC": SpnCity1AgentExecutor,
        "SPN Fault Handling Agent City2 OMC": SpnCity2AgentExecutor,
        "Uncertainty Simulation Agent": UncertaintySimulationAgentExecutor,
    }
    agent_name = agent_card.name
    agent_class = agent2class.get(agent_name)

    if not agent_class:
        logger.info(f"Skipping external agent '{agent_name}': no local executor class defined")
        return

    try:
        agent_impl = agent_class()
    except Exception as e:
        logger.error(f"Failed to initialize agent '{agent_name}': {e}")
        return

    request_handler = DefaultRequestHandler(
        agent_executor=agent_impl,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card
    )
    rest_routes = create_rest_routes(
        request_handler=request_handler
    )

    agent_card_routes = create_agent_card_routes(
        agent_card=agent_card
    )

    app = FastAPI()
    app.routes.extend(agent_card_routes)
    app.routes.extend(rest_routes)

    config = uvicorn.Config(app, host=host, port=port)
    uvicorn_server = uvicorn.Server(config)
    await uvicorn_server.serve()


async def main() -> None:
    try:
        pre_insert_psop()
    except Exception as e:
        logger.error(f"pre_insert_psop failed (agents will still start): {e}")

    try:
        agent_lib = AgentCardLoader(Path(__file__).parent / "agentcard")
        agent_cards = agent_lib.get_all_agent_cards()
    except Exception as e:
        logger.error(f"Failed to load agent cards: {e}")
        return

    factory = None
    try:
        factory = AgentRegistryClientFactory().create_from_env()
    except Exception as e:
        logger.warning(f"Failed to create registry client (agents will start without registration): {e}")

    tasks: List[asyncio.Task] = []
    for agent_card in agent_cards:
        if factory:
            try:
                result = await register_or_update_agent(factory, agent_card)
                logger.info(f"register/update agentcard for {agent_card.name}, result is {result}")
            except Exception as e:
                logger.error(f"register/update agent card failed: {e}")
        agent_name = agent_card.name
        if not agent_card.supported_interfaces:
            logger.warning(f"Skipping agent '{agent_name}': no supported interfaces")
            continue
        parsed = urlparse(agent_card.supported_interfaces[0].url)
        task = asyncio.create_task(
            start_server(agent_card, port=parsed.port, host=parsed.hostname),
            name=f"server_{agent_name}"
        )
        tasks.append(task)
        logger.info(f"Starting server for '{agent_name}' on {agent_card.supported_interfaces[0].url}")
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info(f"Shutting down all servers...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"All servers stopped")


if __name__ == "__main__":
    asyncio.run(main())

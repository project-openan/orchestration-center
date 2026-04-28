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

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_rest_routes, create_agent_card_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI
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


def pre_insert_psop():
    storage = get_workflow_storage()
    for wf_id in storage.list_psops():
        psop = storage.load_psop(wf_id)
        save_handle = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        save_handle.handle(psop)


async def start_server(agent_card: AgentCard, port: int, host: str = "127.0.0.1") -> None:
    agent2class = {
        "RAN Energy Saving Agent": EnergySavingAgentExecutor,
        "Energy Saving Intent Agent": EnergySavingIntentAgentExecutor,
        "Live Streaming Agent": LiveStreamingAgentExecutor,
        "Assurance Agent": AssuranceAgentExecutor,
        "RAN Agent": RanAgentExecutor
    }
    agent_name = agent_card.name
    agent_class = agent2class.get(agent_name)

    if not agent_class:
        raise ValueError(f"unknown Agent : {agent_name}")

    agent_impl = agent_class()

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
    pre_insert_psop()
    agent_lib = AgentCardLoader()
    agent_cards = agent_lib.get_all_agent_cards()
    factory = AgentRegistryClientFactory().create_from_env()

    tasks: List[asyncio.Task] = []
    for agent_card in agent_cards:
        try:
            result = factory.register(agent_card)
            logger.info(f"register agentcard for {agent_card.name}, result is {result}")
        except Exception as e:
            logger.error(f"register agent card failed: {e}")
        agent_name = agent_card.name
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

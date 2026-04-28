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
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from loguru import logger
from typing import List
from urllib.parse import urlparse

from orchestrate.registry_client.client_factory import AgentRegistryClientFactory
from orchestrate import AgentCardLoader
from samples.agents.energy_saving_agent import EnergySavingAgentExecutor
from samples.agents.energy_saving_intent_agent import EnergySavingIntentAgentExecutor
from samples.agents.live_streaming_agent import LiveStreamingAgentExecutor
from samples.agents.assurance_agent import AssuranceAgentExecutor
from samples.agents.ran_agent import RanAgentExecutor

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
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    config = uvicorn.Config(
        server.build(),
        host=host,
        port=port,
        log_level='info'
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()
    logger.info(f"Server for {agent_name} stopped")


async def main() -> None:
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
        parsed = urlparse(agent_card.url)
        task = asyncio.create_task(
            start_server(agent_card, port=parsed.port, host=parsed.hostname),
            name=f"server_{agent_name}"
        )
        tasks.append(task)
        logger.info(f"Starting server for '{agent_name}' on {agent_card.url}")
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

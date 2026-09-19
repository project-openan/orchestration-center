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
import os
import signal
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from a2a.types import AgentCard
from google.protobuf.json_format import MessageToDict
from loguru import logger

from common.custom import HandlerRegistry, InterfaceType
from common.util.config_util import get_conf
from orchestrate import AgentCardLoader
from host_agent.service import start_agent_server
from host_agent.runtime import HostAgentExecutor
from samples.spn_host_agent import SpnControlPoint, SpnExtensionLifecycle
from orchestrate.registry_client.client_factory import AgentRegistryClientFactory
from orchestrate.workflow_storage_instance import get_workflow_storage
from samples.agents.spn_domain_agent import SpnDomainAgentExecutor
from samples.agents.spn_domain_agent_city2 import SpnDomainAgentCity2Executor

# Global list to track all agent executors for graceful shutdown
_agent_executors = []






def _agent_card_to_dict(agent_card: AgentCard) -> dict:
    return MessageToDict(agent_card)


def _override_advertised_host(agent_card: AgentCard, host: str) -> None:
    """Rewrite the host each interface URL advertises (for registration and
    for other containers to call back), independent of what uvicorn binds to.
    Loopback-hardcoded sample agent cards otherwise only work when the caller
    shares the host with the agent process."""
    for iface in agent_card.supported_interfaces:
        if not iface.url:
            continue
        parsed = urlparse(iface.url)
        netloc = f"{host}:{parsed.port}" if parsed.port else host
        iface.url = urlunparse(parsed._replace(netloc=netloc))


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

    storage = get_workflow_storage()
    for wf_id in storage.list_psops():
        psop = storage.load_psop(wf_id)
        if psop is None:
            logger.warning(f"pre_insert_psop: workflow {wf_id} not found, skipping")
            continue
        save_handle = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        save_handle.handle(psop)


async def start_server(
    agent_card: AgentCard,
    port: int,
    host: str = "127.0.0.1",
    all_agent_cards: list[AgentCard] | None = None,
) -> None:
    agent_name = agent_card.name
    try:
        if agent_name == "Host Agent":
            credentials_path = Path(__file__).parent / "agent_credentials.json"
            ssl_verify = str(get_conf().get("client_verify_server", "false")).lower() == "true"
            agent_impl = HostAgentExecutor(
                extension_agent_cards=all_agent_cards,
                control_point_factory=SpnControlPoint,
                extension_lifecycle=SpnExtensionLifecycle(
                    all_agent_cards,
                    str(credentials_path),
                    ssl_verify,
                ),
                credentials_config=str(credentials_path),
            )
        elif agent_name == "SPN Domain Agent City1":
            agent_impl = SpnDomainAgentExecutor()
        elif agent_name == "SPN Domain Agent City2":
            agent_impl = SpnDomainAgentCity2Executor()
        else:
            logger.info(f"Skipping external agent '{agent_name}': no local executor class defined")
            return
        _agent_executors.append(agent_impl)
    except Exception as e:
        logger.error(f"Failed to initialize agent '{agent_name}': {e}")
        return

    await start_agent_server(agent_card, agent_impl, port=port, host=host)


def _warn_if_chat_llm_unconfigured() -> None:
    """Negotiation-capable sample agents need a real chat model. Agents still
    start without one (see common/llm/config/llm_config.py's degrade-not-crash
    guard) but every negotiation call will fail, so make that loud at startup
    instead of leaving it to surface as a per-call error later."""
    try:
        from common.llm.config.llm_config import describe_missing_fields, get_model_config, missing_required_fields

        config = get_model_config("chat")
        missing = missing_required_fields(config) if config else ["url", "model", "api_key"]
        if missing:
            logger.warning(
                f"Sample agents starting without a configured chat LLM: "
                f"{describe_missing_fields('chat', missing)}"
            )
    except Exception as e:
        logger.warning(f"Could not verify chat LLM configuration at startup: {e}")


async def main() -> None:
    _warn_if_chat_llm_unconfigured()

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

    # SAMPLE_AGENTS_HOST lets these cards advertise a Docker service name (or
    # any reachable host) instead of the hardcoded 127.0.0.1 from the JSON,
    # so a container other than this one can reach and register them. Unset,
    # behavior is unchanged (loopback, same-host processes).
    advertise_host = os.environ.get("SAMPLE_AGENTS_HOST", "").strip()
    if advertise_host:
        for agent_card in agent_cards:
            _override_advertised_host(agent_card, advertise_host)
        logger.info(f"Advertising sample agent cards on host '{advertise_host}'")

    factory = None
    try:
        factory = AgentRegistryClientFactory().create_from_env()
    except Exception as e:
        logger.warning(f"Failed to create registry client (agents will start without registration): {e}")

    tasks: list[asyncio.Task] = []
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
        # Bind to all interfaces when advertising a different host (a Docker
        # service name isn't a local bind address); otherwise bind exactly
        # what the card says, matching prior same-host behavior.
        bind_host = "0.0.0.0" if advertise_host else parsed.hostname
        task = asyncio.create_task(
            start_server(
                agent_card,
                port=parsed.port,
                host=bind_host,
                all_agent_cards=agent_cards,
            ),
            name=f"server_{agent_name}"
        )
        tasks.append(task)
        logger.info(f"Starting server for '{agent_name}' on {agent_card.supported_interfaces[0].url}")

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received, stopping all servers...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, signal_handler)

    try:
        # Wait for either all tasks to complete or shutdown signal
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_EXCEPTION,
            timeout=None
        )

        # If we get here due to shutdown signal or exception, cancel pending tasks
        if shutdown_event.is_set() or pending:
            logger.info("Shutting down all servers...")
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            logger.info("All servers stopped")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All servers stopped")
    finally:
        # Shutdown all agent executors
        logger.info(f"Shutting down {len(_agent_executors)} agent executors...")
        for executor in _agent_executors:
            if hasattr(executor, 'shutdown'):
                try:
                    executor.shutdown()
                except Exception as e:
                    logger.warning(f"Error shutting down executor {executor.__class__.__name__}: {e}")
        # Give executors a moment to clean up
        await asyncio.sleep(0.5)
        logger.info("All agent executors shut down")


if __name__ == "__main__":
    asyncio.run(main())

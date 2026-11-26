# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Deterministic A2A fixtures: python -m samples.role_pilot.technical_server."""

import argparse
import asyncio
import json
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor
from a2a.types import AgentCard, Artifact, Part, Task, TaskState, TaskStatus
from google.protobuf.json_format import ParseDict

from host_agent.service import create_agent_app, start_agent_server


def pilot_card(city: str, port: int) -> AgentCard:
    if city not in ("a", "b") or not 1 <= port <= 65535:
        raise ValueError("Expected city a/b and a valid TCP port")
    return ParseDict({
        "name": f"Technical RAN {city.upper()}", "version": "1.0.0",
        "description": "Synthetic routing fixture; no network optimization or business certification",
        "supportedInterfaces": [{"url": f"http://127.0.0.1:{port}", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}],
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
        "skills": [{"id": f"explore-{city}", "name": f"Explore {city.upper()}",
                    "description": "Validate scope and echo routing evidence only", "tags": ["technical-test"]}],
    }, AgentCard())


class TechnicalExecutor(AgentExecutor):
    def __init__(self, city: str, *, scope: dict[str, str] | None = None):
        self.city = city
        self.scope = dict(scope) if scope is not None else {
            "tenant": "technical-demo", "site": f"city-{city}", "business_object": f"ran-{city}",
        }
        if set(self.scope) != {"tenant", "site", "business_object"} or not all(self.scope.values()):
            raise ValueError("Technical scope requires tenant, site, and business_object")

    async def execute(self, context, event_queue):
        try:
            request = json.loads(context.get_user_input())
            expected = {**self.scope, "skill_id": f"explore-{self.city}"}
            if not isinstance(request, dict) or any(request.get(k) != v for k, v in expected.items()):
                raise ValueError("Scope or skill does not match this test instance")
            result = {**expected, "instance_id": f"technical-{self.city}",
                      "agent_name": f"Technical RAN {self.city.upper()}", "technical_only": True}
            state = TaskState.TASK_STATE_COMPLETED
        except (ValueError, TypeError) as exc:
            result = {"technical_only": True, "error": str(exc)}
            state = TaskState.TASK_STATE_FAILED
        await event_queue.enqueue_event(Task(
            id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=state),
            artifacts=[Artifact(artifact_id=str(uuid4()), parts=[Part(text=json.dumps(result))])],
        ))

    async def cancel(self, context, event_queue):
        await event_queue.enqueue_event(Task(id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED)))


def pilot_app(city: str, port: int):
    return create_agent_app(pilot_card(city, port), TechnicalExecutor(city))


async def serve(port_a: int, port_b: int):
    if port_a == port_b:
        raise ValueError("Test instances require different ports")
    await asyncio.gather(*[
        start_agent_server(pilot_card(city, port), TechnicalExecutor(city), port=port)
        for city, port in (("a", port_a), ("b", port_b))
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port-a", type=int, default=18991)
    parser.add_argument("--port-b", type=int, default=18992)
    args = parser.parse_args()
    asyncio.run(serve(args.port_a, args.port_b))

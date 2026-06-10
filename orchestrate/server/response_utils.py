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

import json
from typing import Any, List

from a2a.types import AgentCard
from fastapi import HTTPException
from google.protobuf.json_format import Parse
from loguru import logger

from orchestrate.registry_client.client_factory import AgentRegistryClientFactory
from orchestrate.agentcard_loader import _normalize_agent_dict


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 200, "message": message, "status": "success", "data": data}


def created(data: Any = None, message: str = "created") -> dict:
    return {"code": 201, "message": message, "status": "success", "data": data}


def error(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "status": "error", "data": data}


async def get_agent_cards() -> List[AgentCard]:
    factory = AgentRegistryClientFactory()
    client = factory.create_from_env()
    try:
        raw = await client.list_exact()
        if not raw:
            raise HTTPException(status_code=404, detail="No available agents found")
        return [Parse(json.dumps(_normalize_agent_dict(agent)), AgentCard()) for agent in raw]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch agent cards from registry: {e}")
        raise HTTPException(status_code=503, detail="Agent registry unavailable")
    finally:
        await client.close()

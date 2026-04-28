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
from functools import partial

from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from limits import parse_many, storage, strategies
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from common.config import (
    FLOW_CTL_PARSE_PDF, FLOW_CTL_PLAN, FLOW_CTL_ALL_PSOPS, FLOW_CTL_ONE_PSOP,
    FLOW_CTL_SAVE_PSOP, FLOW_CTL_DELETE_PSOP, FLOW_CTL_AGENT_CARDS,
    FLOW_CTL_GENERATE_PSOP, FLOW_CTL_RETRIEVE_PSOP, FLOW_CTL_START_PROCESS_STREAM,
)
from common.util.config_util import get_conf


class ConnectionLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_connections: int):
        super().__init__(app)
        self.max_connections = max_connections
        self.active_connections = 0
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        async with self._lock:
            if self.active_connections >= self.max_connections:
                logger.error(f"The server is at maximum connection capacity. ({self.max_connections})")
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "code": status.HTTP_503_SERVICE_UNAVAILABLE,
                        "message": f"The server is at maximum connection capacity. ({self.max_connections})"
                    }
                )
            self.active_connections += 1

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Internal Server Error"
                }
            )
        finally:
            async with self._lock:
                self.active_connections -= 1


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout_seconds: int):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        try:
            response = await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
            return response
        except asyncio.TimeoutError:
            logger.error(f"Requests processing timeout. ({self.timeout_seconds} seconds)")
            return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                                content={
                                    "code": status.HTTP_504_GATEWAY_TIMEOUT,
                                    "message": f"Requests processing timeout. ({self.timeout_seconds} seconds)"
                                })


sync_storage = storage.MemoryStorage()
limiter = strategies.MovingWindowRateLimiter(sync_storage)


def parser_rate_lime(interface_name: str, config):
    config_map = {
        "parse_pdf":(FLOW_CTL_PARSE_PDF, 50),
        "plan":(FLOW_CTL_PLAN, 50),
        "get_all_psops":(FLOW_CTL_ALL_PSOPS, 50),
        "get_psop_by_id":(FLOW_CTL_ONE_PSOP, 50),
        "save_psop":(FLOW_CTL_SAVE_PSOP, 50),
        "delete_psop":(FLOW_CTL_DELETE_PSOP, 50),
        "get_all_agent_cards":(FLOW_CTL_AGENT_CARDS, 50),
        "generate_psop_from_intent":(FLOW_CTL_GENERATE_PSOP, 50),
        "retrieve_psop_by_intent":(FLOW_CTL_RETRIEVE_PSOP, 50),
    }

    entry = config_map.get(interface_name)
    if entry is None:
        logger.warning(f"Unknown interface name: {interface_name}, cannot get rate limit")
        return None
    key, default_value = entry
    try:
        rate_value = int(config.get(key, default_value))
    except(ValueError, TypeError):
        logger.error(f"Config key '{key}' has invalid value, using default {default_value}")
        rate_value = default_value
    rate_string = f"{rate_value}/second"
    try:
        items = parse_many(rate_string)
        return items[0] if items else None
    except Exception as e:
        logger.error(f"Failed to parse rate limit string: '{rate_string}': {e}")
        return None


async def async_hit(rate_item, *identifiers: str, cost=1):
    func = partial(limiter.hit, rate_item, *identifiers, cost=cost)
    return await asyncio.to_thread(func)


class RateLimiter:
    def __init__(self, config, interface_name: str = None):
        self.rate_item = parser_rate_lime(interface_name, config)
        if not self.rate_item:
            raise ValueError("Invalid rate limit configuration")

    async def __call__(self, request: Request):
        identifier = request.client.host
        if not await async_hit(self.rate_item, identifier):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
        return True

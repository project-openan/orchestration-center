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

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrate.server.middleware import (
    parse_rate_limit, RateLimiter, async_hit,
    ConnectionLimitMiddleware, TimeoutMiddleware
)
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette import status


class TestParserRateLime:
    @patch('orchestrate.server.middleware.get_conf')
    def test_returns_rate_item_for_valid_interface(self, mock_get_conf):
        mock_get_conf.return_value = {}
        result = parse_rate_limit("parse_pdf", {})
        assert result is not None
        from limits import RateLimitItem
        assert isinstance(result, RateLimitItem)

    @patch('orchestrate.server.middleware.get_conf')
    def test_returns_none_for_unknown_interface(self, mock_get_conf):
        mock_get_conf.return_value = {}
        result = parse_rate_limit("unknown_interface_xyz", {})
        assert result is None

    @patch('orchestrate.server.middleware.get_conf')
    def test_returns_none_when_parse_fails(self, mock_get_conf):
        mock_get_conf.return_value = {}
        with patch('orchestrate.server.middleware.parse_many', side_effect=ValueError("bad")):
            result = parse_rate_limit("parse_pdf", {})
            assert result is None

    @patch('orchestrate.server.middleware.get_conf')
    def test_uses_default_when_config_invalid(self, mock_get_conf):
        config = {"flow_ctl_parallel_parse_pdf": "not_a_number"}
        mock_get_conf.return_value = config
        result = parse_rate_limit("parse_pdf", {"flow_ctl_parallel_parse_pdf": "abc"})
        assert result is not None

    @patch('orchestrate.server.middleware.get_conf')
    def test_new_endpoint_names_mapped(self, mock_get_conf):
        mock_get_conf.return_value = {}
        for name in ("list_workflows", "create_workflow", "sop_orchestrate"):
            result = parse_rate_limit(name, {})
            assert result is not None, f"{name} should map to a rate"


class TestRateLimiter:
    @pytest.mark.anyio
    @patch('orchestrate.server.middleware.get_conf')
    async def test_allows_within_limit(self, mock_get_conf):
        mock_get_conf.return_value = {}
        limiter = RateLimiter({}, "parse_pdf")
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"

        result = await limiter(mock_request)
        assert result is True

    @patch('orchestrate.server.middleware.get_conf')
    def test_raises_for_invalid_interface(self, mock_get_conf):
        mock_get_conf.return_value = {}
        with patch('orchestrate.server.middleware.parse_rate_limit', return_value=None):
            with pytest.raises(ValueError, match="Invalid rate limit configuration"):
                RateLimiter({}, "nonexistent")


@pytest.mark.anyio
class TestConnectionLimitMiddleware:
    async def test_accepts_when_under_limit(self):
        app = MagicMock()
        middleware = ConnectionLimitMiddleware(app, max_connections=10)
        mock_request = MagicMock(spec=Request)

        async def call_next(req):
            return PlainTextResponse("ok")

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200

    async def test_rejects_when_at_limit(self):
        app = MagicMock()
        middleware = ConnectionLimitMiddleware(app, max_connections=0)

        async def call_next(req):
            return PlainTextResponse("ok")

        mock_request = MagicMock(spec=Request)
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 503
        body = json.loads(response.body)
        assert "maximum connection capacity" in body["message"]

    async def test_releases_on_exception(self):
        app = MagicMock()
        middleware = ConnectionLimitMiddleware(app, max_connections=5)
        mock_request = MagicMock(spec=Request)

        async def call_next(req):
            raise ValueError("boom")

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 500
        assert middleware.active_connections == 0

    async def test_concurrent_limit_enforced(self):
        app = MagicMock()
        middleware = ConnectionLimitMiddleware(app, max_connections=1)

        async def slow_call(req):
            await asyncio.sleep(0.05)
            return PlainTextResponse("ok")

        async def make_request():
            mock_req = MagicMock(spec=Request)
            return await middleware.dispatch(mock_req, slow_call)

        results = await asyncio.gather(make_request(), make_request(), make_request())
        statuses = [r.status_code for r in results]
        assert 200 in statuses
        assert 503 in statuses


@pytest.mark.anyio
class TestTimeoutMiddleware:
    async def test_passes_within_timeout(self):
        app = MagicMock()
        middleware = TimeoutMiddleware(app, timeout_seconds=5)
        mock_request = MagicMock()
        mock_request.url.path = "/rest/v1/orchestrate/workflows"

        async def call_next(req):
            return PlainTextResponse("ok")

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200

    async def test_returns_504_on_timeout(self):
        app = MagicMock()
        middleware = TimeoutMiddleware(app, timeout_seconds=0.01)
        mock_request = MagicMock()
        mock_request.url.path = "/rest/v1/orchestrate/workflows"

        async def slow_call(req):
            await asyncio.sleep(1.0)
            return PlainTextResponse("ok")

        response = await middleware.dispatch(mock_request, slow_call)
        assert response.status_code == 504
        body = json.loads(response.body)
        assert "timeout" in body["message"].lower()

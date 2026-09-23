# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the generic Host Agent workflow repository adapter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from host_agent.workflow_repository import OrchestrationWorkflowRepository


@pytest.mark.asyncio
async def test_find_loads_first_match_and_forwards_connection_options(monkeypatch):
    search = AsyncMock(return_value=[
        SimpleNamespace(workflow_id="best-match"),
        SimpleNamespace(workflow_id="second-match"),
    ])
    load = AsyncMock(return_value=object())
    monkeypatch.setattr("host_agent.workflow_repository.search_psop", search)
    monkeypatch.setattr("host_agent.workflow_repository.load_psop", load)
    repository = OrchestrationWorkflowRepository(
        orch_url="https://orch.example/", ssl_verify=True
    )

    result = await repository.find("diagnose the network")

    assert result is load.return_value
    search.assert_awaited_once_with(
        "https://orch.example", "diagnose the network", top_n=3, ssl_verify=True
    )
    load.assert_awaited_once_with(
        "https://orch.example", "best-match", ssl_verify=True
    )


@pytest.mark.asyncio
async def test_find_without_matches_does_not_load_a_workflow(monkeypatch):
    search = AsyncMock(return_value=[])
    load = AsyncMock()
    monkeypatch.setattr("host_agent.workflow_repository.search_psop", search)
    monkeypatch.setattr("host_agent.workflow_repository.load_psop", load)
    repository = OrchestrationWorkflowRepository(orch_url="https://orch.example")

    with pytest.raises(RuntimeError, match="No matching workflow found"):
        await repository.find("unknown intent")

    load.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_forwards_id_and_default_tls_option(monkeypatch):
    load = AsyncMock(return_value=SimpleNamespace(id="wf-42"))
    monkeypatch.setattr("host_agent.workflow_repository.load_psop", load)
    repository = OrchestrationWorkflowRepository(orch_url="http://orch.example/")

    result = await repository.get("wf-42")

    assert result.id == "wf-42"
    load.assert_awaited_once_with(
        "http://orch.example", "wf-42", ssl_verify=False
    )


@pytest.mark.asyncio
async def test_get_propagates_sdk_load_failure(monkeypatch):
    load = AsyncMock(side_effect=ConnectionError("orchestration unavailable"))
    monkeypatch.setattr("host_agent.workflow_repository.load_psop", load)
    repository = OrchestrationWorkflowRepository(orch_url="https://orch.example")

    with pytest.raises(ConnectionError, match="orchestration unavailable"):
        await repository.get("wf-42")

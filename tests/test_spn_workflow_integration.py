# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

import pytest
from a2a_t.core import MetadataContent
from a2a_t.core.metadata import NEGOTIATION_T_EXTENSION_URI, TASK_T_EXTENSION_URI
from samples.spn_host_agent.content import (
    PRIVATE_LINE_COMPLAINT_URI,
    metadata_for,
    task_content,
)
from workflow_engine import BusinessInput, ReceivedArtifact, ReceivedMessage, TaskRequest


class _TaskContentClient:
    def generate_task_prompt_from_data_with_schema(self, data, schema, template_uri):
        del schema
        prompt = (
            "## 任务对象(Task Object)\n"
            f"{data['任务对象']}\n\n"
            "## 任务上下文(Task Context)\n"
            f"{data['任务上下文']}"
        )
        return MetadataContent(template_uri, prompt, TASK_T_EXTENSION_URI)


def _request(step_name: str) -> TaskRequest:
    return TaskRequest(
        execution_id="execution-1",
        task_id=f"task-{step_name}",
        input=BusinessInput.from_text("执行专线投诉诊断"),
        agent_name="agent",
        skill="diagnosis",
        instruction="执行专线投诉诊断",
        step_name=step_name,
    )


def test_task_content_only_city1_requires_negotiation():
    client = _TaskContentClient()

    city1 = task_content(client, _request("diagnosis_city1"))
    city2 = task_content(client, _request("diagnosis_city2"))

    city1_prompt = city1.metadata[TASK_T_EXTENSION_URI]
    city2_prompt = city2.metadata[TASK_T_EXTENSION_URI]
    assert "## 任务对象(Task Object)\n接入端口名称：\n" in city1_prompt
    assert "P781-" not in city1_prompt
    assert "P882-珠江新城-PTN7900-23-TPA1EG24-11(cvlan=200)" in city2_prompt
    assert city1.metadata["templateUri"] == PRIVATE_LINE_COMPLAINT_URI
    assert city1.extensions == frozenset({TASK_T_EXTENSION_URI})


def test_metadata_for_accepts_identical_task_and_artifact_copies():
    metadata = {
        NEGOTIATION_T_EXTENSION_URI: "proposal",
        "templateUri": "Negotiation-T/network-layer/information-negotiation-propose/v1",
    }
    received = ReceivedMessage(
        task_metadata=metadata,
        artifacts=(ReceivedArtifact(artifact_id="artifact-1", metadata=metadata),),
    )

    assert metadata_for(received, NEGOTIATION_T_EXTENSION_URI) == metadata


def test_metadata_for_ignores_unrelated_layer_metadata():
    protocol_metadata = {
        NEGOTIATION_T_EXTENSION_URI: "proposal",
        "templateUri": "Negotiation-T/information-negotiation/propose/v1",
    }
    received = ReceivedMessage(
        task_metadata={**protocol_metadata, "taskOnly": "task-value"},
        artifacts=(
            ReceivedArtifact(
                artifact_id="artifact-1",
                metadata={**protocol_metadata, "artifactOnly": "artifact-value"},
            ),
        ),
    )

    assert metadata_for(received, NEGOTIATION_T_EXTENSION_URI) == protocol_metadata


def test_metadata_for_rejects_conflicting_protocol_copies():
    received = ReceivedMessage(
        task_metadata={NEGOTIATION_T_EXTENSION_URI: "proposal-a"},
        artifacts=(
            ReceivedArtifact(
                artifact_id="artifact-1",
                metadata={NEGOTIATION_T_EXTENSION_URI: "proposal-b"},
            ),
        ),
    )

    with pytest.raises(ValueError, match="Conflicting"):
        metadata_for(received, NEGOTIATION_T_EXTENSION_URI)

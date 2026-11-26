# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import Mock

import fitz
import httpx
from workflow_engine.core.models import Workflow
from workflow_engine.core.workflow_validator import find_workflow_errors

from common.llm.config.model_sources import load_model_configs
from common.llm.provider.generic_llm import GenericLLM
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.psop_generator import PsopGenerator
from orchestrate.solution_package.vision_generation import parse_visual_chapter


def test_visual_parse_uses_full_text_and_numbered_page_images(tmp_path):
    source = tmp_path / "spg.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Context outside the flow")
        pdf.new_page().insert_text((30, 30), "Original workflow")
        pdf.set_toc([[1, "4. Architecture", 1], [1, "6. Interaction Flow", 2]])
        pdf.save(source)
    model = Mock()
    model.ask_with_images.return_value = "", "# Interaction Flow"
    assert parse_visual_chapter(source, llm=model) == ("6. Interaction Flow", "# Interaction Flow")
    prompt, images = model.ask_with_images.call_args.args
    assert "Context outside the flow" in prompt and "Original workflow" in prompt
    assert "[1, 2]" in prompt
    assert len(images) == 2 and all(image[:2] == bytes([255, 216]) for image in images)


def test_visual_spg_preserves_the_available_branch_without_bypassing_an_omitted_approval(monkeypatch):
    from a2a.types import AgentCard, AgentSkill

    def step(name, skill, edges, layer=0, context_from=None):
        return {"name": name, "layer": layer, "context_from": context_from,
                "subtasks": [{"agent": "Desk", "skill": skill, "description": f"Execute {name}"}],
                "next": [{"step": target, "condition": condition} for target, condition in edges]}

    generated = {"name": "SPG", "user_intent": "Model-generated intent summary", "steps": [
        step("diagnosis", "Analyze", [("approval", "A change is required"), ("report", "No change is required")]),
        step("approval", "unmatched", [("apply_change", "The change was approved")]),
        step("apply_change", "Change", [("end", "")], 1, ["approval"]),
        step("report", "Report", [("end", "")]),
    ]}
    model = Mock()
    model.ask_llm.return_value = "", json.dumps(generated)
    monkeypatch.setattr("orchestrate.core.psop_generator.get_llm_instance", lambda: model)
    cards = [AgentCard(name="Desk", skills=[AgentSkill(id=name, name=name) for name in ("Analyze", "Change", "Report")])]
    output = PsopGenerator().generate_psop_workflow(
        PreFlow(name="SPG", steps_md="Diagnose, approve changes, or report"), cards, visual_spg=True)
    assert [step.name for step in output.steps] == ["diagnosis", "report"]
    assert output.user_intent is None
    prompt = model.ask_llm.call_args.args[0]
    assert "## SPG PreFlow" in prompt
    assert "## Visual SPG rules" in prompt
    assert "## User Intent" not in prompt and '"user_intent"' not in prompt
    assert [(edge.step, edge.condition) for edge in output.steps[0].next] == [
        ("report", "No change is required"),
    ]
    assert not find_workflow_errors(Workflow.from_dict(output.model_dump(mode="json")))


def test_yaml_opt_in_and_multimodal_payload(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_text(
        "models:\n  chat:\n    model: synthetic\n    url: https://example.invalid/chat\n"
        "    input_modalities: [text, image]\n", encoding="utf-8",
    )
    client = GenericLLM(load_model_configs(path=path)["chat"])
    received = {}

    def endpoint(request):
        received.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(endpoint))
    assert client.ask_with_images("Read it", [b"jpeg"])[1] == "OK"
    assert received["messages"][0]["content"] == [
        {"type": "text", "text": "Read it"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,anBlZw=="}},
    ]
    client.ask_llm("Still text")
    assert received["messages"][0]["content"] == "Still text"

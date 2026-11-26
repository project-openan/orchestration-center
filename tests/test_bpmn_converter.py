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

"""Unit tests for the PSOP -> BPMN 2.0 converter (orchestrate.core.bpmn_converter).

The converter is the engine behind the BPMN query endpoints: it takes a
retrieved PSOP and produces a self-contained BPMN 2.0 XML document. These
tests pin the mapping rules (start/end events, per-step tasks, gateways for
multi-branch jumps, conditionExpressions, DI section) and the defensive
behaviour (dangling jumps, cycles, empty steps).
"""

import pytest
from xml.etree import ElementTree as ET

from orchestrate.core.bpmn_converter import psop_to_bpmn
from orchestrate.core.model.psop import PSOP, Step, Task, JumpCondition, StepType

BPMN_NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
DI_EDGE_TAG = ".//{http://www.omg.org/spec/BPMN/20100524/DI}BPMNEdge"
DI_SHAPE_TAG = ".//{http://www.omg.org/spec/BPMN/20100524/DI}BPMNShape"
DI_WAYPOINT_TAG = "{http://www.omg.org/spec/DD/20100524/DI}waypoint"
DC_BOUNDS_TAG = "{http://www.omg.org/spec/DD/20100524/DC}Bounds"


def _task(description="do it", agent="agent_a", skill="skill_a"):
    return Task(description=description, agent=agent, skill=skill)


def _linear_psop(**kwargs):
    """step1 -> step2 -> step3, no branches."""
    defaults = dict(
        id="wf-linear",
        name="Linear Workflow",
        steps=[
            Step(name="step1", subtasks=[_task()], next=[JumpCondition(step="step2", condition="")]),
            Step(name="step2", subtasks=[_task()], next=[JumpCondition(step="step3", condition="")]),
            Step(name="step3", subtasks=[_task()]),
        ],
    )
    defaults.update(kwargs)
    return PSOP(**defaults)


def _parse(psop):
    return ET.fromstring(psop_to_bpmn(psop))


class TestBasicStructure:
    def test_output_is_parseable_xml_with_declarations(self):
        xml = psop_to_bpmn(_linear_psop())
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        root = ET.fromstring(xml)
        assert root.tag == f"{{{BPMN_NS['b']}}}definitions"

    def test_process_copies_psop_identity(self):
        root = _parse(_linear_psop())
        process = root.find(".//b:process", BPMN_NS)
        assert process.get("id") == "Process_wf-linear"
        assert process.get("name") == "Linear Workflow"
        assert process.get("isExecutable") == "false"

    def test_one_task_per_step_with_step_names(self):
        root = _parse(_linear_psop())
        tasks = root.findall(".//b:task", BPMN_NS)
        assert [t.get("name") for t in tasks] == ["step1", "step2", "step3"]

    def test_start_and_end_events_exist(self):
        root = _parse(_linear_psop())
        assert root.find(".//b:startEvent", BPMN_NS) is not None
        assert root.find(".//b:endEvent", BPMN_NS) is not None

    def test_psop_description_is_process_documentation(self):
        root = _parse(_linear_psop(description="整体描述"))
        process = root.find(".//b:process", BPMN_NS)
        doc = process.find("b:documentation", BPMN_NS)
        assert doc is not None and doc.text == "整体描述"


class TestStepDocumentation:
    def test_documentation_records_type_agent_and_skill(self):
        psop = PSOP(
            id="wf-doc",
            name="Doc WF",
            steps=[
                Step(
                    name="only",
                    type=StepType.ANY_SUCCESS,
                    layer=1,
                    context_from=["up"],
                    subtasks=[_task(description="采集日志", agent="采集Agent", skill="collect")],
                ),
            ],
        )
        root = _parse(psop)
        doc = root.find(".//b:task/b:documentation", BPMN_NS).text
        assert "Step type: AnySuccess" in doc
        assert "采集日志" in doc
        assert "agent: 采集Agent" in doc
        assert "skill: collect" in doc
        assert "Layer: 1" in doc
        assert "Context from: up" in doc


class TestBranching:
    def test_single_next_is_plain_sequence_flow_without_gateway(self):
        root = _parse(_linear_psop())
        assert root.find(".//b:exclusiveGateway", BPMN_NS) is None
        flows = root.findall(".//b:sequenceFlow", BPMN_NS)
        # start->step1, step1->step2, step2->step3, step3->end
        assert len(flows) == 4

    def test_multiple_jumps_create_exclusive_gateway_with_conditions(self):
        psop = PSOP(
            id="wf-branch",
            name="Branch WF",
            steps=[
                Step(
                    name="decide",
                    subtasks=[_task()],
                    next=[
                        JumpCondition(step="fast", condition="耗时 < 5 分钟"),
                        JumpCondition(step="slow", condition="耗时 >= 5 分钟"),
                    ],
                ),
                Step(name="fast", subtasks=[_task()]),
                Step(name="slow", subtasks=[_task()]),
            ],
        )
        root = _parse(psop)
        gateways = root.findall(".//b:exclusiveGateway", BPMN_NS)
        assert len(gateways) == 1
        conditions = root.findall(".//b:conditionExpression", BPMN_NS)
        assert len(conditions) == 2
        texts = [c.text for c in conditions]
        assert "耗时 < 5 分钟" in texts
        assert all(c.get(f"{{{XSI_NS}}}type") == "bpmn:tFormalExpression" for c in conditions)
        # flows: start->decide, decide->gw, gw->fast, gw->slow, fast->end, slow->end
        assert len(root.findall(".//b:sequenceFlow", BPMN_NS)) == 6

    def test_unconditional_branch_becomes_gateway_default(self):
        psop = PSOP(
            id="wf-default",
            name="Default WF",
            steps=[
                Step(
                    name="decide",
                    subtasks=[_task()],
                    next=[
                        JumpCondition(step="special", condition="命中规则"),
                        JumpCondition(step="fallback", condition=""),
                    ],
                ),
                Step(name="special", subtasks=[_task()]),
                Step(name="fallback", subtasks=[_task()]),
            ],
        )
        root = _parse(psop)
        gateway = root.find(".//b:exclusiveGateway", BPMN_NS)
        assert gateway.get("default") is not None
        # only the non-default branch carries a conditionExpression
        assert len(root.findall(".//b:conditionExpression", BPMN_NS)) == 1

    def test_exit_steps_flow_into_end_event(self):
        psop = PSOP(
            id="wf-two-exits",
            name="Two Exits",
            steps=[
                Step(name="a", subtasks=[_task()]),
                Step(name="b", subtasks=[_task()]),
            ],
        )
        root = _parse(psop)
        end_id = root.find(".//b:endEvent", BPMN_NS).get("id")
        targets = [f.get("targetRef") for f in root.findall(".//b:sequenceFlow", BPMN_NS)]
        assert targets.count(end_id) == 2

    def test_multiple_entry_steps_flow_from_start_event(self):
        psop = PSOP(
            id="wf-two-entries",
            name="Two Entries",
            steps=[
                Step(name="a", subtasks=[_task()]),
                Step(name="b", subtasks=[_task()]),
            ],
        )
        root = _parse(psop)
        start_id = root.find(".//b:startEvent", BPMN_NS).get("id")
        sources = [f.get("sourceRef") for f in root.findall(".//b:sequenceFlow", BPMN_NS)]
        assert sources.count(start_id) == 2


class TestDefensiveBehaviour:
    def test_dangling_jump_target_is_skipped(self):
        psop = PSOP(
            id="wf-dangling",
            name="Dangling",
            steps=[
                Step(name="a", subtasks=[_task()], next=[JumpCondition(step="ghost", condition="x")]),
            ],
        )
        root = _parse(psop)
        # the dangling flow is dropped; step a still exits to the end event
        refs = [f.get("targetRef") for f in root.findall(".//b:sequenceFlow", BPMN_NS)]
        assert "ghost" not in "".join(refs)
        assert root.find(".//b:exclusiveGateway", BPMN_NS) is None

    def test_cycle_does_not_hang_and_all_steps_get_shapes(self):
        psop = PSOP(
            id="wf-cycle",
            name="Cycle",
            steps=[
                Step(name="a", subtasks=[_task()], next=[JumpCondition(step="b", condition="")]),
                Step(name="b", subtasks=[_task()], next=[JumpCondition(step="a", condition="retry")]),
            ],
        )
        root = _parse(psop)
        assert len(root.findall(".//b:task", BPMN_NS)) == 2
        assert len(root.findall(DI_SHAPE_TAG)) == 4  # start + 2 tasks + end

    def test_cycle_only_workflow_still_connects_start(self):
        psop = PSOP(
            id="wf-cycle-only",
            name="Cycle Only",
            steps=[
                Step(name="a", subtasks=[_task()], next=[JumpCondition(step="b", condition="")]),
                Step(name="b", subtasks=[_task()], next=[JumpCondition(step="a", condition="")]),
            ],
        )
        root = _parse(psop)
        start_id = root.find(".//b:startEvent", BPMN_NS).get("id")
        sources = [f.get("sourceRef") for f in root.findall(".//b:sequenceFlow", BPMN_NS)]
        assert sources.count(start_id) == 1

    def test_special_characters_are_escaped(self):
        psop = _linear_psop(name='<Weird "&-Name>', description="desc <with> tags")
        root = _parse(psop)  # would raise on malformed XML if escaping were broken
        assert root.find(".//b:process", BPMN_NS).get("name") == '<Weird "&-Name>'

    def test_chinese_and_symbol_step_names_produce_valid_ids(self):
        psop = _linear_psop(
            id="中文 id",
            steps=[
                Step(name="步骤 1", subtasks=[_task()]),
                Step(name="2nd step", subtasks=[_task()]),
            ],
        )
        root = _parse(psop)
        process = root.find(".//b:process", BPMN_NS)
        assert process.get("id").startswith("Process_")
        assert all(ch.isalnum() or ch in "_-." for ch in process.get("id"))

    def test_empty_steps_raise_value_error(self):
        with pytest.raises(ValueError):
            psop_to_bpmn(PSOP(id="wf-empty", name="Empty", steps=[]))

    def test_none_psop_raises_value_error(self):
        with pytest.raises(ValueError):
            psop_to_bpmn(None)


class TestDiagramInterchange:
    def test_di_section_covers_all_nodes_and_flows(self):
        psop = PSOP(
            id="wf-di",
            name="DI WF",
            steps=[
                Step(
                    name="decide",
                    subtasks=[_task()],
                    next=[
                        JumpCondition(step="x", condition="a"),
                        JumpCondition(step="y", condition=""),
                    ],
                ),
                Step(name="x", subtasks=[_task()]),
                Step(name="y", subtasks=[_task()]),
            ],
        )
        xml = psop_to_bpmn(psop)
        root = ET.fromstring(xml)
        flow_count = len(root.findall(".//b:sequenceFlow", BPMN_NS))
        node_count = len(root.findall(".//b:task", BPMN_NS)) \
            + len(root.findall(".//b:exclusiveGateway", BPMN_NS)) \
            + len(root.findall(".//b:startEvent", BPMN_NS)) \
            + len(root.findall(".//b:endEvent", BPMN_NS))
        assert len(root.findall(DI_SHAPE_TAG)) == node_count
        assert len(root.findall(DI_EDGE_TAG)) == flow_count

    def test_waypoints_connect_source_right_to_target_left(self):
        root = _parse(_linear_psop())
        edges = root.findall(DI_EDGE_TAG)
        assert edges, "DI edges missing"
        for edge in edges:
            wps = edge.findall(DI_WAYPOINT_TAG)
            assert len(wps) == 2
            x1, y1 = int(wps[0].get("x")), int(wps[0].get("y"))
            x2, y2 = int(wps[1].get("x")), int(wps[1].get("y"))
            assert x2 > x1  # layered layout flows left -> right

    def test_downstream_steps_are_laid_out_to_the_right(self):
        root = _parse(_linear_psop())
        shapes = {s.get("bpmnElement"): s for s in root.findall(DI_SHAPE_TAG)}
        def task_x(name):
            # find task id by name then read its shape bounds
            for task in root.findall(".//b:task", BPMN_NS):
                if task.get("name") == name:
                    bounds = shapes[task.get("id")].find(DC_BOUNDS_TAG)
                    return int(bounds.get("x"))
        assert task_x("step1") < task_x("step2") < task_x("step3")

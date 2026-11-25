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

"""
PSOP -> BPMN 2.0 converter.

Converts a stored PSOP workflow into a BPMN 2.0 XML document that standard
BPMN tooling (Camunda Modeler, bpmn.io, Yaoqiang, ...) can open. The BPMN
query endpoints are a pure post-processing view of the retrieved PSOP: they
load the PSOP through the normal retrieval path and convert it here, so BPMN
never needs its own storage.

Mapping rules:

- PSOP workflow            -> one ``bpmn:process`` (``isExecutable="false"``)
- Workflow start           -> one ``bpmn:startEvent`` linked to every step that
                              has no incoming jump (entry steps)
- PSOP step                -> one ``bpmn:task`` named after the step; the step
                              success condition (AllSuccess / AnySuccess /
                              SelfLoop) and the subtasks (description, agent,
                              skill) are recorded as ``bpmn:documentation``
- ``Step.next`` jumps      -> ``bpmn:sequenceFlow``; a step with more than one
                              outgoing jump gets an ``bpmn:exclusiveGateway``
                              so the conditional branches remain valid BPMN,
                              and each jump condition becomes a
                              ``conditionExpression``
- Steps without ``next``   -> linked to one ``bpmn:endEvent``
- Layout                   -> a BPMNDiagram / BPMNPlane DI section with a
                              layered layout (topological depth -> x, order ->
                              y) so viewers can render the process without a
                              layout engine
"""

import re
from collections import Counter, defaultdict, deque
from typing import Dict, List, Tuple
from urllib.parse import quote
from xml.etree import ElementTree as ET

from loguru import logger

from orchestrate.core.model.psop import PSOP

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

for _prefix, _uri in (("bpmn", BPMN_NS), ("bpmndi", BPMNDI_NS), ("dc", DC_NS), ("di", DI_NS), ("xsi", XSI_NS)):
    ET.register_namespace(_prefix, _uri)

def _b(tag: str) -> str:
    return f"{{{BPMN_NS}}}{tag}"

# Shape geometry (pixels, the de-facto bpmn.io grid)
TASK_W, TASK_H = 100, 80
GATEWAY_W, GATEWAY_H = 50, 50
EVENT_W, EVENT_H = 36, 36
GATEWAY_GAP_X = 60
LAYER_GAP_X = 240
ROW_GAP_Y = 140
ORIGIN_X, ORIGIN_Y = 200, 160

# Jump-condition texts that mean "always take this branch" -- such flows stay
# plain sequence flows (a single one is marked as the gateway default) instead
# of carrying a conditionExpression.
_UNCONDITIONAL_HINTS = ("无条件", "默认", "otherwise", "default", "none", "n/a", "-")

_EMPTY_DOC = "n/a"


def _sanitize_id(raw: str, prefix: str) -> str:
    """Build an NCName-safe element id (ASCII letters/digits/_/-/. only)."""
    cleaned = "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "_-." else "_" for ch in str(raw or ""))
    if not cleaned or not (cleaned[0].isascii() and cleaned[0].isalpha()):
        cleaned = f"N{cleaned}"
    return f"{prefix}{cleaned}"


def _is_unconditional(condition: str) -> bool:
    text = (condition or "").strip().lower()
    if not text:
        return True
    return any(hint in text for hint in _UNCONDITIONAL_HINTS)


def bpmn_content_disposition(psop: PSOP) -> str:
    """RFC 6266 Content-Disposition value for the converted BPMN download.

    HTTP headers must be latin-1 encodable while PSOP names are frequently
    Chinese, so the value carries an ASCII fallback in ``filename`` plus an
    RFC 5987 ``filename*=UTF-8''`` parameter with the percent-encoded name.
    """
    raw = psop.name or psop.id or "workflow"
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", str(raw))[:128].strip("_") or "workflow"
    ascii_name = cleaned.encode("ascii", "ignore").decode("ascii").strip("_") or "workflow"
    utf8_name = quote(f"{cleaned}.bpmn", safe="")
    return f'inline; filename="{ascii_name}.bpmn"; filename*=UTF-8\'\'{utf8_name}'


def _step_documentation(step) -> str:
    """Human-readable documentation block describing one PSOP step."""
    lines = [f"Step type: {step.type.value}"]
    subtasks = step.subtasks or []
    if not subtasks:
        lines.append("Subtasks: none")
    for index, task in enumerate(subtasks, start=1):
        lines.append(
            f"Subtask {index}: {task.description or _EMPTY_DOC} "
            f"(agent: {task.agent or _EMPTY_DOC}, skill: {task.skill or _EMPTY_DOC})"
        )
    if step.layer:
        lines.append(f"Layer: {step.layer} (aggregation)")
        if step.context_from:
            lines.append(f"Context from: {', '.join(step.context_from)}")
    return "\n".join(lines)


def _collect_graph(psop: PSOP):
    """Return (steps_by_name, entries, exits, edges, outgoing_count).

    edges is a list of ``(source_name, target_name, condition)``. Dangling
    jump targets (not present in ``psop.steps``) are skipped so stored PSOPs
    that predate topology validation still convert instead of crashing.
    """
    steps_by_name = {step.name: step for step in psop.steps}
    edges: List[Tuple[str, str, str]] = []
    incoming_count: Counter = Counter()
    outgoing_count: Dict[str, int] = {step.name: 0 for step in psop.steps}
    for step in psop.steps:
        for jump in step.next or []:
            target = jump.step
            if target not in steps_by_name:
                logger.warning(f"[BPMN] Skipping dangling jump target '{target}' from step '{step.name}'")
                continue
            edges.append((step.name, target, jump.condition or ""))
            outgoing_count[step.name] += 1
            incoming_count[target] += 1
    entries = [step.name for step in psop.steps if incoming_count[step.name] == 0]
    exits = [step.name for step in psop.steps if outgoing_count[step.name] == 0]
    return steps_by_name, entries, exits, edges, outgoing_count


def _layered_rows(psop: PSOP, entries: List[str], edges) -> Dict[str, Tuple[int, int]]:
    """Assign each step a ``(depth, row)`` grid slot for the DI section.

    Depth is the longest-path distance from the nearest entry step (Kahn's
    algorithm; back edges inside cycles are ignored so the sort terminates);
    row is the position within the depth column.
    """
    successors = defaultdict(list)
    pending_incoming = Counter()
    for src, dst, _cond in edges:
        successors[src].append(dst)
        pending_incoming[dst] += 1

    queue = deque(entries)
    depth = {name: 0 for name in entries}
    order: List[str] = []
    while queue:
        name = queue.popleft()
        order.append(name)
        for succ in successors[name]:
            depth[succ] = max(depth.get(succ, 0), depth[name] + 1)
            pending_incoming[succ] -= 1
            if pending_incoming[succ] == 0:
                queue.append(succ)

    # Cycle members never reach pending_incoming == 0: keep them at depth 0
    # after the DAG part so every step still gets a shape.
    for step in psop.steps:
        depth.setdefault(step.name, 0)
        if step.name not in order:
            order.append(step.name)

    rows: Dict[str, Tuple[int, int]] = {}
    per_depth: Dict[int, int] = {}
    for name in order:
        d = depth[name]
        r = per_depth.get(d, 0)
        rows[name] = (d, r)
        per_depth[d] = r + 1
    return rows


def psop_to_bpmn(psop: PSOP) -> str:
    """Convert a PSOP workflow into a BPMN 2.0 XML document (UTF-8 string)."""
    if psop is None or not getattr(psop, "steps", None):
        raise ValueError("PSOP has no steps to convert to BPMN")

    steps_by_name, entries, exits, edges, outgoing_count = _collect_graph(psop)
    rows = _layered_rows(psop, entries, edges)
    # A workflow made only of cycles has no entry step; anchor the start event
    # on the first step so the diagram stays connected.
    if not entries:
        entries = [psop.steps[0].name]

    process_id = _sanitize_id(psop.id or "psop", "Process_")
    definitions_id = _sanitize_id(psop.id or "psop", "Definitions_")
    process_name = psop.name or process_id

    step_ids = {step.name: f"Step_{i}" for i, step in enumerate(psop.steps, start=1)}

    definitions = ET.Element(
        _b("definitions"),
        {
            "id": definitions_id,
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "exporter": "OpenAN Orchestration Center",
            "exporterVersion": "1.0",
        },
    )
    process = ET.SubElement(
        definitions,
        _b("process"),
        {"id": process_id, "name": process_name, "isExecutable": "false"},
    )
    if psop.description:
        ET.SubElement(process, _b("documentation")).text = psop.description

    # node_id -> element; node_id -> flow-id lists for incoming/outgoing refs
    elements: Dict[str, ET.Element] = {}
    incoming_refs: Dict[str, List[str]] = defaultdict(list)
    outgoing_refs: Dict[str, List[str]] = defaultdict(list)
    # node_id -> (x, y, w, h) for the DI section
    shapes: Dict[str, Tuple[int, int, int, int]] = {}
    flows: List[dict] = []  # {id, source_ref, target_ref, conditional}

    def add_flow(source_ref: str, target_ref: str, condition: str = "", conditional: bool = False) -> str:
        flow_id = f"Flow_{len(flows) + 1}"
        attrs = {"id": flow_id, "sourceRef": source_ref, "targetRef": target_ref}
        flow = ET.SubElement(process, _b("sequenceFlow"), attrs)
        if conditional:
            expr = ET.SubElement(flow, _b("conditionExpression"))
            expr.set(f"{{{XSI_NS}}}type", "bpmn:tFormalExpression")
            expr.text = condition or "true"
        flows.append({"id": flow_id, "source": source_ref, "target": target_ref})
        outgoing_refs[source_ref].append(flow_id)
        incoming_refs[target_ref].append(flow_id)
        return flow_id

    # ── start event ──
    start_y = ORIGIN_Y + rows[entries[0]][1] * ROW_GAP_Y + (TASK_H - EVENT_H) // 2
    start_x = ORIGIN_X - 80
    elements["Start_1"] = ET.SubElement(
        process, _b("startEvent"), {"id": "Start_1", "name": f"{process_name} start"}
    )
    shapes["Start_1"] = (start_x, start_y, EVENT_W, EVENT_H)
    for entry in entries:
        add_flow("Start_1", step_ids[entry])

    # ── one task per PSOP step ──
    for step in psop.steps:
        step_id = step_ids[step.name]
        depth, row = rows[step.name]
        x = ORIGIN_X + depth * LAYER_GAP_X
        y = ORIGIN_Y + row * ROW_GAP_Y
        task = ET.SubElement(process, _b("task"), {"id": step_id, "name": step.name or step_id})
        ET.SubElement(task, _b("documentation")).text = _step_documentation(step)
        elements[step_id] = task
        shapes[step_id] = (x, y, TASK_W, TASK_H)

    # ── branch structure: per-step gateway when the step has several jumps ──
    for step in psop.steps:
        jumps = [j for j in (step.next or []) if j.step in steps_by_name]
        step_id = step_ids[step.name]
        if not jumps:
            continue
        if len(jumps) == 1:
            add_flow(step_id, step_ids[jumps[0].step], jumps[0].condition,
                     conditional=not _is_unconditional(jumps[0].condition))
            continue
        gateway_id = f"GW_{step_id}"
        gateway = ET.SubElement(
            process,
            _b("exclusiveGateway"),
            {"id": gateway_id, "name": f"{step.name} branches"},
        )
        elements[gateway_id] = gateway
        depth, row = rows[step.name]
        gx = ORIGIN_X + depth * LAYER_GAP_X + TASK_W + GATEWAY_GAP_X
        gy = ORIGIN_Y + row * ROW_GAP_Y + (TASK_H - GATEWAY_H) // 2
        shapes[gateway_id] = (gx, gy, GATEWAY_W, GATEWAY_H)
        add_flow(step_id, gateway_id)
        default_target = next((j.step for j in jumps if _is_unconditional(j.condition)), None)
        for jump in jumps:
            conditional = not _is_unconditional(jump.condition)
            flow_id = add_flow(gateway_id, step_ids[jump.step], jump.condition, conditional=conditional)
            if jump.step == default_target:
                gateway.set("default", flow_id)

    # ── end event + flows from exit steps ──
    max_depth = max((rows[s.name][0] for s in psop.steps), default=0)
    end_x = ORIGIN_X + (max_depth + 1) * LAYER_GAP_X
    first_exit_row = rows[exits[0]][1] if exits else 0
    end_y = ORIGIN_Y + first_exit_row * ROW_GAP_Y + (TASK_H - EVENT_H) // 2
    elements["End_1"] = ET.SubElement(process, _b("endEvent"), {"id": "End_1", "name": "end"})
    shapes["End_1"] = (end_x, end_y, EVENT_W, EVENT_H)
    for exit_step in exits:
        add_flow(step_ids[exit_step], "End_1")

    # ── incoming/outgoing reference children (BPMN tFlowNode syntax) ──
    for node_id, node in elements.items():
        for flow_id in incoming_refs.get(node_id, []):
            ET.SubElement(node, _b("incoming")).text = flow_id
        for flow_id in outgoing_refs.get(node_id, []):
            ET.SubElement(node, _b("outgoing")).text = flow_id

    # ── DI: shapes + edge waypoints so viewers can render the process ──
    diagram = ET.SubElement(definitions, f"{{{BPMNDI_NS}}}BPMNDiagram", {"id": f"DIA_{process_id}"})
    plane = ET.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane", {"id": f"PLANE_{process_id}", "bpmnElement": process_id})
    for node_id, (x, y, w, h) in shapes.items():
        shape = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNShape", {"id": f"SHAPE_{node_id}", "bpmnElement": node_id})
        ET.SubElement(shape, f"{{{DC_NS}}}Bounds", {"x": str(x), "y": str(y), "width": str(w), "height": str(h)})
    for flow in flows:
        sx, sy, sw, sh = shapes[flow["source"]]
        tx, ty, _tw, th = shapes[flow["target"]]
        x1, y1 = sx + sw, sy + sh / 2
        x2, y2 = tx, ty + th / 2
        edge = ET.SubElement(plane, f"{{{BPMNDI_NS}}}BPMNEdge", {"id": f"EDGE_{flow['id']}", "bpmnElement": flow["id"]})
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", {"x": str(int(x1)), "y": str(int(y1))})
        ET.SubElement(edge, f"{{{DI_NS}}}waypoint", {"x": str(int(x2)), "y": str(int(y2))})

    xml_body = ET.tostring(definitions, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body

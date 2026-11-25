# -*- coding: utf-8 -*-
"""Generate workflow plans for WorfBench items using mainstream frameworks.

Runs in the FRAMEWORK venv (D:\\OpenAN\\framework-venv). Every framework gets
the same underlying model (blue-zone gateway glm-5.3-flash) and the same task
set; each uses its NATURAL abstraction to produce a plan:

- crewai      : CrewPlanner (hierarchical planning) - the only native NL planner
- langgraph   : StateGraph with a planner node (scaffold + unified prompt)
- agents      : OpenAI Agents SDK Agent with structured plan output
- ag2         : ConversableAgent with unified prompt

Plan JSON contract: {"id", "instruction", "nodes": [str], "edges": [[i, j]]}.

Usage:
    python gen_plans.py --framework crewai --items <items-take.jsonl> --out <plans_dir>
"""
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

GATEWAY_BASE = "https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1"
GATEWAY_MODEL = "glm-5.3-flash"
# Endpoint/model/key are env-overridable so the same script can drive either
# the blue-zone gateway (GLM) or DeepSeek direct (full-coverage speed runs).
BASE_URL = os.environ.get("FW_LLM_BASE_URL", GATEWAY_BASE)
MODEL = os.environ.get("FW_LLM_MODEL", GATEWAY_MODEL)
API_KEY = os.environ.get("FW_LLM_API_KEY", "")

PLAN_PROMPT = """You are a workflow planner. Decompose the task below into an ordered list of executable subtasks using ONLY the available actions.

## Task
{instruction}

## Available actions
{actions}

## Output
{output_spec}"""

DESCRIPTION_SPEC = """Return ONLY a JSON object: {{"nodes": ["subtask description", ...], "edges": [[from_index, to_index], ...]}}.
"nodes" are subtask descriptions in execution order; "edges" are dependency pairs of node indices (empty list if independent)."""

SKILL_SPEC = """Return ONLY a JSON object: {{"nodes": ["<action name>", ...], "edges": [[from_index, to_index], ...]}}.
Each node MUST be the EXACT action name copied verbatim from the Available actions list (never paraphrase, never invent);
"edges" are dependency pairs of node indices (empty list if independent)."""


def gateway_key() -> str:
    env_key = os.environ.get("FW_LLM_API_KEY", "")
    if env_key:
        return env_key
    cred = Path.home() / ".dsh" / ".credentials.yaml"
    match = re.search(
        r"LANQU_GATEWAY_API_KEY\s*[:=]\s*[\"']?([A-Za-z0-9._\-]+)",
        cred.read_text(encoding="utf-8"),
    )
    if not match:
        raise SystemExit("no LLM API key: set FW_LLM_API_KEY or provide ~/.dsh/.credentials.yaml")
    return match.group(1)


def render_prompt(item: dict) -> str:
    actions = "\n".join(f"- {name}: {desc}" for name, desc in item["actions"].items())
    spec = SKILL_SPEC if item.get("granularity") == "skill" else DESCRIPTION_SPEC
    return PLAN_PROMPT.format(instruction=item["instruction"], actions=actions, output_spec=spec)


def parse_plan(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text or "", re.DOTALL)
    payload = fenced.group(1).strip() if fenced else (text or "").strip()
    start = min((i for i in (payload.find("{"), payload.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("no JSON in plan response")
    candidate = payload[start:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        value = json.loads(candidate[: candidate.rfind("}") + 1])
    if isinstance(value, list):
        value = {"nodes": value, "edges": []}
    nodes = [str(n).strip() for n in value.get("nodes", []) if str(n).strip()]
    edges = [[int(a), int(b)] for a, b in value.get("edges", []) if isinstance(a, int)]
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# framework generators
# ---------------------------------------------------------------------------


def gen_crewai(item: dict) -> dict:
    """CrewAI hierarchical planning via CrewPlanner (native NL planner)."""
    from crewai import Agent, Crew, Task
    from crewai.crews import CrewOutputs
    from crewai.llm import LLM
    from crewai.planning.crew_planner import CrewPlanner

    llm = LLM(model=f"openai/{MODEL}", base_url=BASE_URL, api_key=gateway_key())
    actions = list(item["actions"])
    worker = Agent(
        role="Operations Executor",
        goal="Execute the planned step precisely using the assigned action.",
        backstory="A precise operator that follows the plan.",
        llm=llm,
        allow_delegation=False,
    )
    tasks = [Task(description="Execute the workflow plan end to end.", agent=worker, expected_output="Result summary.")]
    crew = Crew(agents=[worker], tasks=tasks, process="hierarchical", manager_llm=llm, planning=True)
    planner = CrewPlanner(crew, {"query": item["instruction"]})
    plan = planner.plan()
    nodes = []
    for planned_task in plan.get("tasks", []):
        description = getattr(planned_task, "description", "") or ""
        nodes.append(description.strip())
    edges = [[i, i + 1] for i in range(len(nodes) - 1)]
    return {"nodes": nodes, "edges": edges}


def gen_langgraph(item: dict) -> dict:
    """LangGraph StateGraph with a planner node."""
    from langchain_openai import ChatOpenAI
    from langgraph.graph import StateGraph, END
    from typing_extensions import TypedDict

    llm = ChatOpenAI(
        model=MODEL, base_url=BASE_URL, api_key=gateway_key(), timeout=240
    )

    class PlanState(TypedDict):
        prompt: str
        plan: dict

    def planner_node(state: PlanState) -> dict:
        response = llm.invoke(state["prompt"])
        return {"plan": parse_plan(response.content)}

    graph = StateGraph(PlanState)
    graph.add_node("planner", planner_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", END)
    app = graph.compile()
    result = app.invoke({"prompt": render_prompt(item), "plan": {}})
    return result["plan"]


def gen_agents_sdk(item: dict) -> dict:
    """OpenAI Agents SDK: Agent with instruction-based JSON plan output.

    (Strict output_type=Plan schemas are rejected by DeepSeek with 400;
    instruction-based JSON + parse_plan is the portable equivalent.)
    """
    from agents import Agent, Runner, set_default_openai_client, set_tracing_disabled
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=BASE_URL, api_key=gateway_key())
    set_default_openai_client(client)
    set_tracing_disabled(True)

    agent = Agent(
        name="WorkflowPlanner",
        model=MODEL,
        instructions="You are a workflow planner. Follow the user template exactly and output ONLY the JSON plan object.",
    )
    result = Runner.run_sync(agent, render_prompt(item))
    final = result.final_output
    return parse_plan(final if isinstance(final, str) else str(final))


def gen_ag2(item: dict) -> dict:
    """Modern AutoGen (autogen-agentchat): AssistantAgent tool-less planner."""
    import asyncio

    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(
        model=MODEL,
        base_url=BASE_URL,
        api_key=gateway_key(),
        model_info={"vision": False, "function_calling": True, "json_output": True, "family": "unknown"},
    )
    agent = AssistantAgent(
        "planner",
        model_client=client,
        system_message="You are a workflow planner. Output only the JSON plan requested.",
    )

    async def _run() -> str:
        try:
            result = await agent.run(task=render_prompt(item))
            return result.messages[-1].content
        finally:
            close = getattr(client, "close", None)
            if close:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass

    reply = asyncio.run(_run())
    return parse_plan(reply if isinstance(reply, str) else str(reply))


GENERATORS = {
    "crewai": gen_crewai,
    "langgraph": gen_langgraph,
    "agents": gen_agents_sdk,
    "ag2": gen_ag2,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", required=True, choices=sorted(GENERATORS))
    parser.add_argument("--items", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()

    os.environ.setdefault("OPENAI_API_KEY", gateway_key())
    os.environ.setdefault("OPENAI_BASE_URL", BASE_URL)

    generator = GENERATORS[args.framework]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = [
        json.loads(line) for line in Path(args.items).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if args.shard_count > 1:
        items = [
            item for index, item in enumerate(items)
            if index % args.shard_count == args.shard_index
        ]
    ok = failed = 0
    for item in items:
        dest = out_dir / f"{item['id']}.json"
        if dest.exists():
            ok += 1
            continue
        started = time.time()
        try:
            plan = generator(item)
            plan.update({"id": item["id"], "instruction": item["instruction"]})
            dest.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
            ok += 1
            print(f"  [{item['id']}] OK ({time.time() - started:.0f}s, {len(plan['nodes'])} nodes)", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  [{item['id']}] FAIL: {type(exc).__name__}: {str(exc)[:140]} ({time.time() - started:.0f}s)", flush=True)
    print(f"{args.framework}: ok={ok} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


from types import SimpleNamespace

import pytest
from workflow_engine import (
    BusinessInput,
    ControlPoint,
    MessageContent,
    NegotiationReply,
    RouteDecision,
    TaskRequest,
    TaskResult,
)
from workflow_engine.control.control_points import EventType

from orchestrate.core.model.psop import PSOP, JumpCondition, Step, StepType, Task
from orchestrate.sandbox import StubAgentRuntime, StubScenario, StubTemplate, run_sandbox

TASK_T = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"


def _request(step="step_1", index=0, agent="agent-a", skill="skill-a"):
    return TaskRequest(
        execution_id="execution-1",
        task_id=f"task-{step}-{index}",
        input=BusinessInput.from_text("input"),
        agent_name=agent,
        skill=skill,
        instruction=f"instruction {step}",
        step_name=step,
    )


def _card(name="agent-a"):
    return SimpleNamespace(
        name=name,
        description="SPN diagnosis capability",
        capabilities=SimpleNamespace(extensions=[SimpleNamespace(uri=TASK_T)]),
        skills=[SimpleNamespace(id="skill-a", name="skill-a", description="SPN skill")],
    )


class _QueueEventCallback:
    def __init__(self):
        self.events = []

    def on_event(self, event_type, data):
        self.events.append((event_type, data))


@pytest.mark.asyncio
async def test_template_priority_is_specific_to_generic():
    runtime = StubAgentRuntime(
        [_card()],
        templates=[
            StubTemplate(response_text="generic"),
            StubTemplate(card_name="agent-a", response_text="card default"),
            StubTemplate(agent="agent-a", response_text="agent"),
            StubTemplate(agent="agent-a", skill="skill-a", response_text="agent skill"),
            StubTemplate(step="step_1", subtask_index=0, response_text="step override"),
        ],
    )
    first = await runtime.dispatch(_request(), MessageContent.text("request"))
    second = await runtime.dispatch(_request(step="step_2"), MessageContent.text("request"))

    assert first.text == "step override"
    assert second.text == "agent skill"


@pytest.mark.asyncio
async def test_stub_response_has_task_t_protocol_shape_and_events():
    callback = _QueueEventCallback()
    runtime = StubAgentRuntime([_card()])
    runtime.begin_execution("execution-1", None, callback)
    result = await runtime.dispatch(_request(), MessageContent.text("request"))
    runtime.end_execution("execution-1")

    assert result.task_state == "TASK_STATE_COMPLETED"
    assert result.received_messages[0].task_metadata[TASK_T]
    assert [event[0] for event in callback.events] == [
        EventType.AGENT_REQUEST,
        EventType.AGENT_RESPONSE,
    ]
    assert runtime.stub_interactions[0].scenario == StubScenario.SUCCESS


@pytest.mark.asyncio
async def test_stub_error_returns_mapped_failure():
    callback = _QueueEventCallback()
    runtime = StubAgentRuntime(
        [_card()],
        templates=[StubTemplate(scenario=StubScenario.ERROR, response_text="injected failure")],
    )
    runtime.begin_execution("execution-1", None, callback)
    result = await runtime.dispatch(_request(), MessageContent.text("request"))

    assert result.task_state == "TASK_STATE_FAILED"
    assert result.failure_code == "stub.task_failed"
    assert runtime.stub_interactions[0].error_code == "stub.task_failed"


@pytest.mark.asyncio
async def test_stub_negotiation_invokes_control_point():
    callback = _QueueEventCallback()
    runtime = StubAgentRuntime([_card()], scenario=StubScenario.NEGOTIATION)

    class _Callbacks:
        async def on_negotiation(self, request):
            return NegotiationReply.send(MessageContent.text("accept proposal"))

    runtime.begin_execution("execution-1", None, callback)
    result = await runtime.dispatch(_request(), MessageContent.text("request"), _Callbacks())

    assert result.task_state == "TASK_STATE_COMPLETED"
    assert runtime.stub_interactions[0].negotiation_rounds == 1
    assert [event[0] for event in callback.events] == [
        EventType.AGENT_REQUEST,
        EventType.NEGOTIATION_REQUEST,
        EventType.NEGOTIATION_RESOLVED,
        EventType.AGENT_RESPONSE,
    ]


class _SandboxControlPoint(ControlPoint):
    async def on_task(self, request):
        return MessageContent.text(f"content for {request.step_name}")

    async def on_self_task(self, request):
        return TaskResult.succeeded((f"merged {request.step_name}",))

    async def on_route(self, request):
        return RouteDecision.allow("sandbox edge")


class _BusinessControlPointFailsForArbitrarySteps(ControlPoint):
    async def on_task(self, request):
        raise ValueError("No business input configured")

    async def on_self_task(self, request):
        return TaskResult.succeeded()

    async def on_route(self, request):
        return RouteDecision.allow("sandbox edge")


def _psop():
    return PSOP(
        name="sandbox flow",
        steps=[
            Step(
                name="diagnose",
                subtasks=[Task(description="diagnose", agent="agent-a", skill="skill-a")],
                next=[JumpCondition(step="merge", condition="")],
            ),
            Step(
                name="merge",
                type=StepType.SELF_LOOP,
                context_from=["diagnose"],
                subtasks=[Task(description="merge", agent="workbench", skill="merge")],
                next=[JumpCondition(step="endNode", condition="")],
            ),
        ],
    )


def _parallel_psop():
    return PSOP(
        name="parallel sandbox flow",
        steps=[
            Step(
                name="diagnose_city1",
                subtasks=[Task(description="diagnose city1", agent="agent-a", skill="skill-a")],
                next=[JumpCondition(step="merge", condition="")],
            ),
            Step(
                name="diagnose_city2",
                subtasks=[Task(description="diagnose city2", agent="agent-a", skill="skill-a")],
                next=[JumpCondition(step="merge", condition="")],
            ),
            Step(
                name="merge",
                type=StepType.SELF_LOOP,
                context_from=["diagnose_city1", "diagnose_city2"],
                subtasks=[Task(description="merge results", agent="workbench", skill="merge")],
                next=[JumpCondition(step="endNode", condition="")],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_sandbox_runner_executes_dag_and_records_context():
    report = await run_sandbox(
        _psop(),
        [_card()],
        _SandboxControlPoint(),
        runtime_intent="run sandbox",
    )

    assert report.verdict.value == "pass"
    assert report.execution_path == ["diagnose", "merge"]
    merge_trace = next(trace for trace in report.context_trace if trace.step == "merge")
    assert merge_trace.upstream_steps == ["diagnose"]
    assert merge_trace.upstream_result_count == 1
    assert len(report.stub_interactions) == 1
    assert report.error is None


@pytest.mark.asyncio
async def test_sandbox_does_not_generate_real_business_content():
    psop = PSOP(
        name="arbitrary workflow",
        steps=[
            Step(
                name="step1",
                subtasks=[Task(description="diagnose", agent="agent-a", skill="skill-a")],
                next=[JumpCondition(step="endNode", condition="")],
            )
        ],
    )
    report = await run_sandbox(
        psop,
        [_card()],
        _BusinessControlPointFailsForArbitrarySteps(),
    )

    assert report.verdict.value == "pass"
    assert report.stub_interactions[0].task_state == "TASK_STATE_COMPLETED"


@pytest.mark.asyncio
async def test_parallel_sandbox_e2e_records_parallel_path_and_merge_context():
    report = await run_sandbox(
        _parallel_psop(),
        [_card()],
        _SandboxControlPoint(),
        runtime_intent="run parallel sandbox",
    )

    assert report.verdict.value == "pass"
    assert set(report.execution_path[:2]) == {"diagnose_city1", "diagnose_city2"}
    assert report.execution_path[-1] == "merge"
    assert len(report.stub_interactions) == 2
    merge_trace = next(trace for trace in report.context_trace if trace.step == "merge")
    assert set(merge_trace.upstream_steps) == {"diagnose_city1", "diagnose_city2"}
    assert merge_trace.upstream_result_count == 2


@pytest.mark.asyncio
async def test_sandbox_runner_reports_injected_error():
    report = await run_sandbox(
        _psop(),
        [_card()],
        _SandboxControlPoint(),
        scenario=StubScenario.ERROR,
        lang="en",
    )

    assert report.verdict.value == "fail"
    assert report.stub_interactions[0].error_code == "stub.task_failed"
    assert any("intentional Stub error" in risk for risk in report.risks)
    assert any(risk.startswith("Step diagnose failed:") for risk in report.risks)


@pytest.mark.asyncio
async def test_any_success_continues_when_one_subtask_fails():
    psop = PSOP(
        name="any success flow",
        steps=[
            Step(
                name="diagnose",
                type=StepType.ANY_SUCCESS,
                subtasks=[
                    Task(description="failing diagnosis", agent="agent-a", skill="skill-a"),
                    Task(description="successful diagnosis", agent="agent-a", skill="skill-a"),
                ],
                next=[JumpCondition(step="endNode", condition="")],
            )
        ],
    )
    templates = [
        StubTemplate(step="diagnose", subtask_index=0, scenario=StubScenario.ERROR),
        StubTemplate(step="diagnose", subtask_index=1),
    ]
    report = await run_sandbox(
        psop,
        [_card()],
        _SandboxControlPoint(),
        templates=templates,
    )

    assert report.verdict.value == "pass"
    assert len(report.stub_interactions) == 2
    assert report.stub_interactions[0].scenario == StubScenario.ERROR
    assert report.stub_interactions[1].scenario == StubScenario.SUCCESS

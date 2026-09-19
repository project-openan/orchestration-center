from types import SimpleNamespace

from orchestrate.core.model.psop import PSOP, JumpCondition, Step, StepType, Task
from orchestrate.validation.sandbox_validator import (
    SandboxCheckStatus,
    validate_sandbox_static,
)

TASK_T = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"
NEGOTIATION_T = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Negotiation-T/v1"


def _step(name, agents=("agent-a",), next_steps=(), context_from=None, step_type=StepType.ALL_SUCCESS):
    return Step(
        name=name,
        subtasks=[
            Task(description=f"diagnose {name}", agent=agent, skill=f"skill-{name}")
            for agent in agents
        ],
        next=[JumpCondition(step=target, condition="") for target in next_steps],
        context_from=context_from,
        type=step_type,
    )


def _workflow(*steps):
    return PSOP(name="sandbox workflow", steps=list(steps))


def _card(name="agent-a", extensions=(TASK_T,), skills=("skill-a",)):
    return SimpleNamespace(
        name=name,
        capabilities=SimpleNamespace(
            extensions=[SimpleNamespace(uri=uri) for uri in extensions],
        ),
        skills=[SimpleNamespace(id=skill, name=skill, description=skill) for skill in skills],
    )


def test_reports_cycle_and_unreachable_steps():
    report = validate_sandbox_static(_workflow(
        _step("a", next_steps=("b",)),
        _step("b", next_steps=("a",)),
        _step("orphan"),
    ))

    cycle = next(check for check in report.checks if check.check_id == "structure.cycle")
    assert cycle.status == SandboxCheckStatus.FAIL
    assert set(cycle.affected) == {"a", "b"}
    reachability = next(check for check in report.checks if check.check_id == "structure.reachability")
    assert reachability.status == SandboxCheckStatus.WARNING
    assert "orphan" in reachability.affected
    assert report.verdict == SandboxCheckStatus.FAIL


def test_reports_invalid_context_and_structure():
    report = validate_sandbox_static(_workflow(
        _step("a", next_steps=("b",)),
        _step("b", context_from=["missing"]),
    ), lang="en")

    context = next(check for check in report.checks if check.check_id == "structure.context_sources")
    assert context.status == SandboxCheckStatus.FAIL
    assert any("does not exist" in issue for issue in context.evidence)
    assert report.model_dump()["workflow_id"]


def test_reports_missing_agent_and_extension_capabilities():
    report = validate_sandbox_static(
        _workflow(
            _step("missing", agents=("missing",)),
            _step("a", agents=("agent-a",)),
        ),
        [_card(extensions=())],
    )

    missing = next(check for check in report.checks if check.check_id == "agents.missing")
    task_t = next(check for check in report.checks if check.check_id == "agents.task_t_extension")
    assert missing.status == SandboxCheckStatus.FAIL
    assert task_t.status == SandboxCheckStatus.FAIL
    assert report.verdict == SandboxCheckStatus.FAIL


def test_reports_skill_mismatch_without_failing_workflow():
    report = validate_sandbox_static(
        _workflow(_step("a")),
        [_card(skills=("different-skill",))],
    )

    skill = next(check for check in report.checks if check.check_id == "agents.skill_match")
    assert skill.status == SandboxCheckStatus.WARNING
    assert report.verdict == SandboxCheckStatus.WARNING


def test_all_checks_pass_for_matching_workflow():
    report = validate_sandbox_static(
        _workflow(
            _step("a", next_steps=("merge",)),
            _step("merge", context_from=["a"], step_type=StepType.SELF_LOOP),
        ),
        [_card()],
    )

    assert report.verdict == SandboxCheckStatus.PASS
    assert all(check.status == SandboxCheckStatus.PASS for check in report.checks)

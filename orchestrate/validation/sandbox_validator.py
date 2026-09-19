"""Static and capability validation for sandbox workflow verification."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from orchestrate.core.model.psop import PSOP, Step, StepType
from orchestrate.sandbox.i18n import translate

TASK_T_URI = "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Task-T/v1"
NEGOTIATION_T_URI = (
    "https://projects.tmforum.org/a2aproject/telecommunication/extensions/Negotiation-T/v1"
)
TERMINAL_ROUTES = {"end", "retry", "endNode"}


def _message(lang: str, key: str, **params: Any) -> str:
    return translate(lang, f"checks.{key}", **params)


class SandboxCheckStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class SandboxCheck(BaseModel):
    check_id: str
    status: SandboxCheckStatus
    detail: str
    affected: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class SandboxStaticReport(BaseModel):
    workflow_id: str
    workflow_name: str
    verdict: SandboxCheckStatus
    checks: list[SandboxCheck] = Field(default_factory=list)
    dag_summary: dict[str, Any] = Field(default_factory=dict)


def _check(
    check_id: str,
    status: SandboxCheckStatus,
    detail: str,
    *,
    affected: Iterable[str] | None = None,
    evidence: Iterable[str] | None = None,
    suggestions: Iterable[str] | None = None,
) -> SandboxCheck:
    return SandboxCheck(
        check_id=check_id,
        status=status,
        detail=detail,
        affected=list(affected or []),
        evidence=list(evidence or []),
        suggestions=list(suggestions or []),
    )


def _build_graph(steps: list[Step]) -> tuple[dict[str, list[str]], set[str], set[str]]:
    edges: dict[str, list[str]] = defaultdict(list)
    has_incoming: set[str] = set()
    for step in steps:
        for jump in step.next or []:
            if jump.step in TERMINAL_ROUTES:
                continue
            edges[step.name].append(jump.step)
            has_incoming.add(jump.step)
    sources = {step.name for step in steps} - has_incoming
    has_any_outgoing = {step.name for step in steps if step.next}
    sinks = {
        step.name for step in steps
        if not edges[step.name] and step.name not in has_any_outgoing
    }
    return dict(edges), sources, sinks


def _detect_cycle(steps: list[Step], edges: dict[str, list[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visited:
            return None
        visited.add(node)
        active.add(node)
        path.append(node)
        for target in edges.get(node, []):
            if target in active:
                index = path.index(target)
                return path[index:] + [target]
            cycle = visit(target)
            if cycle:
                return cycle
        path.pop()
        active.remove(node)
        return None

    for step in steps:
        cycle = visit(step.name)
        if cycle:
            return cycle
    return None


def _reachable(steps: list[Step], edges: dict[str, list[str]], sources: set[str]) -> set[str]:
    reachable: set[str] = set()
    queue = deque(sources)
    while queue:
        node = queue.popleft()
        if node in reachable:
            continue
        reachable.add(node)
        queue.extend(edges.get(node, []))
    return reachable


def _ancestors(steps: list[Step], step_name: str) -> set[str]:
    incoming: dict[str, set[str]] = {step.name: set() for step in steps}
    for step in steps:
        for jump in step.next or []:
            if jump.step in incoming:
                incoming[jump.step].add(step.name)

    ancestors: set[str] = set()
    queue = deque(incoming.get(step_name, set()))
    while queue:
        node = queue.popleft()
        if node in ancestors:
            continue
        ancestors.add(node)
        queue.extend(incoming.get(node, set()))
    return ancestors


def _structure_checks(psop: PSOP, lang: str = "zh") -> tuple[list[SandboxCheck], dict[str, Any]]:
    checks: list[SandboxCheck] = []
    steps = psop.steps
    names = [step.name for step in steps]
    name_counts = Counter(names)
    edges, sources, sinks = _build_graph(steps)

    blank = [name for name in names if not name.strip()]
    checks.append(_check(
        "structure.blank_step_name",
        SandboxCheckStatus.FAIL if blank else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.blank_step_name.detail_fail" if blank else "structure.blank_step_name.detail_pass",
        ),
        affected=blank,
        suggestions=[
            _message(lang, "structure.blank_step_name.suggestion")
        ] if blank else None,
    ))

    duplicates = sorted(name for name, count in name_counts.items() if count > 1)
    checks.append(_check(
        "structure.duplicate_step",
        SandboxCheckStatus.FAIL if duplicates else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.duplicate_step.detail_fail" if duplicates else "structure.duplicate_step.detail_pass",
        ),
        affected=duplicates,
        evidence=[
            _message(
                lang,
                "structure.duplicate_step.evidence_occurrences",
                name=name,
                count=name_counts[name],
            )
            for name in duplicates
        ],
        suggestions=[
            _message(lang, "structure.duplicate_step.suggestion")
        ] if duplicates else None,
    ))

    empty_steps = [step.name for step in steps if not step.subtasks]
    checks.append(_check(
        "structure.empty_subtasks",
        SandboxCheckStatus.FAIL if empty_steps else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.empty_subtasks.detail_fail" if empty_steps else "structure.empty_subtasks.detail_pass",
        ),
        affected=empty_steps,
        suggestions=[
            _message(lang, "structure.empty_subtasks.suggestion")
        ] if empty_steps else None,
    ))

    invalid_targets: list[str] = []
    unknown_targets: list[str] = []
    duplicate_edges: list[str] = []
    known = set(names)
    for step in steps:
        seen: set[str] = set()
        for jump in step.next or []:
            if jump.step in TERMINAL_ROUTES:
                continue
            edge = f"{step.name}->{jump.step}"
            if not jump.step.strip():
                invalid_targets.append(edge)
            if jump.step not in known:
                unknown_targets.append(edge)
            if jump.step in seen:
                duplicate_edges.append(edge)
            seen.add(jump.step)

    checks.append(_check(
        "structure.next_targets",
        SandboxCheckStatus.FAIL if invalid_targets or unknown_targets or duplicate_edges else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.next_targets.detail_fail"
            if invalid_targets or unknown_targets or duplicate_edges
            else "structure.next_targets.detail_pass",
        ),
        affected=invalid_targets + unknown_targets + duplicate_edges,
        evidence=invalid_targets + unknown_targets + duplicate_edges,
        suggestions=[_message(lang, "structure.next_targets.suggestion")],
    ))

    cycle = _detect_cycle(steps, edges)
    checks.append(_check(
        "structure.cycle",
        SandboxCheckStatus.FAIL if cycle else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.cycle.detail_fail" if cycle else "structure.cycle.detail_pass",
            path=" -> ".join(cycle or []),
        ),
        affected=cycle or [],
        evidence=cycle or [],
        suggestions=[
            _message(lang, "structure.cycle.suggestion")
        ] if cycle else None,
    ))

    reachable = _reachable(steps, edges, sources)
    unreachable = sorted(known - reachable)
    isolated = sorted(known.intersection(sources, sinks))
    checks.append(_check(
        "structure.reachability",
        SandboxCheckStatus.WARNING if unreachable or isolated else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.reachability.detail_fail" if unreachable or isolated else "structure.reachability.detail_pass",
        ),
        affected=unreachable + isolated,
        evidence=(
            [
                _message(lang, "structure.reachability.evidence_unreachable", name=name)
                for name in unreachable
            ]
            + [
                _message(lang, "structure.reachability.evidence_isolated", name=name)
                for name in isolated
            ]
        ),
        suggestions=[
            _message(lang, "structure.reachability.suggestion")
        ] if unreachable or isolated else None,
    ))

    context_issues: list[str] = []
    for step in steps:
        context_from = step.context_from or []
        if "*" in context_from and len(context_from) != 1:
            context_issues.append(_message(
                lang,
                "structure.context_sources.evidence_wildcard",
                step=step.name,
            ))
        ancestors = _ancestors(steps, step.name)
        for source in context_from:
            if source == "*":
                continue
            if source not in known:
                context_issues.append(_message(
                    lang,
                    "structure.context_sources.evidence_missing",
                    step=step.name,
                    source=source,
                ))
            elif source not in ancestors:
                context_issues.append(
                    _message(
                        lang,
                        "structure.context_sources.evidence_not_ancestor",
                        step=step.name,
                        source=source,
                    )
                )

    checks.append(_check(
        "structure.context_sources",
        SandboxCheckStatus.FAIL if context_issues else SandboxCheckStatus.PASS,
        _message(
            lang,
            "structure.context_sources.detail_fail" if context_issues else "structure.context_sources.detail_pass",
        ),
        affected=context_issues,
        evidence=context_issues,
        suggestions=[
            _message(lang, "structure.context_sources.suggestion")
        ] if context_issues else None,
    ))

    return checks, {
        "nodes": sorted(known),
        "edges": {source: sorted(targets) for source, targets in edges.items()},
        "sources": sorted(sources),
        "sinks": sorted(sinks),
    }


def _extension_uris(card: Any) -> set[str]:
    capabilities = getattr(card, "capabilities", None)
    extensions = getattr(capabilities, "extensions", ()) if capabilities else ()
    return {getattr(extension, "uri", "") for extension in extensions}


def _skills(card: Any) -> set[str]:
    values: set[str] = set()
    for skill in getattr(card, "skills", ()) or ():
        values.update(
            value for value in (
                getattr(skill, "id", ""),
                getattr(skill, "name", ""),
                getattr(skill, "description", ""),
            ) if value
        )
    return values


def _requires_negotiation(task_description: str, skill: str) -> bool:
    text = f"{task_description} {skill}".lower()
    return "negotiation" in text or "协商" in text


def _agent_checks(psop: PSOP, agent_cards: Iterable[Any], lang: str = "zh") -> list[SandboxCheck]:
    cards = list(agent_cards)
    card_names = [getattr(card, "name", "") for card in cards]
    duplicates = sorted(name for name, count in Counter(card_names).items() if count > 1 and name)
    card_by_name = {getattr(card, "name", ""): card for card in cards}
    checks: list[SandboxCheck] = []

    if duplicates:
        checks.append(_check(
            "agents.duplicate_card",
            SandboxCheckStatus.WARNING,
            _message(lang, "agents.duplicate_card.detail"),
            affected=duplicates,
            evidence=duplicates,
            suggestions=[_message(lang, "agents.duplicate_card.suggestion")],
        ))

    missing_agents: list[str] = []
    skill_mismatches: list[str] = []
    missing_task_t: list[str] = []
    missing_negotiation_t: list[str] = []

    for step in psop.steps:
        for index, task in enumerate(step.subtasks):
            key = f"{step.name}.subtasks[{index}].{task.agent}"
            card = card_by_name.get(task.agent)
            if step.type == StepType.SELF_LOOP:
                continue
            if card is None:
                missing_agents.append(key)
                continue

            extensions = _extension_uris(card)
            if TASK_T_URI not in extensions:
                missing_task_t.append(key)
            if _requires_negotiation(task.description, task.skill) and NEGOTIATION_T_URI not in extensions:
                missing_negotiation_t.append(key)
            if task.skill.strip() and task.skill not in _skills(card):
                skill_mismatches.append(key)

    if missing_agents:
        checks.append(_check(
            "agents.missing",
            SandboxCheckStatus.FAIL,
            _message(lang, "agents.missing.detail_fail"),
            affected=missing_agents,
            evidence=missing_agents,
            suggestions=[_message(lang, "agents.missing.suggestion")],
        ))
    else:
        checks.append(_check(
            "agents.missing",
            SandboxCheckStatus.PASS,
            _message(lang, "agents.missing.detail_pass"),
        ))

    if skill_mismatches:
        checks.append(_check(
            "agents.skill_match",
            SandboxCheckStatus.WARNING,
            _message(lang, "agents.skill_match.detail_fail"),
            affected=skill_mismatches,
            evidence=skill_mismatches,
            suggestions=[_message(lang, "agents.skill_match.suggestion")],
        ))
    else:
        checks.append(_check(
            "agents.skill_match",
            SandboxCheckStatus.PASS,
            _message(lang, "agents.skill_match.detail_pass"),
        ))

    if missing_task_t:
        checks.append(_check(
            "agents.task_t_extension",
            SandboxCheckStatus.FAIL,
            _message(lang, "agents.task_t_extension.detail_fail"),
            affected=missing_task_t,
            evidence=missing_task_t,
            suggestions=[_message(lang, "agents.task_t_extension.suggestion")],
        ))
    else:
        checks.append(_check(
            "agents.task_t_extension",
            SandboxCheckStatus.PASS,
            _message(lang, "agents.task_t_extension.detail_pass"),
        ))

    if missing_negotiation_t:
        checks.append(_check(
            "agents.negotiation_t_extension",
            SandboxCheckStatus.WARNING,
            _message(lang, "agents.negotiation_t_extension.detail_fail"),
            affected=missing_negotiation_t,
            evidence=missing_negotiation_t,
            suggestions=[_message(lang, "agents.negotiation_t_extension.suggestion")],
        ))
    else:
        checks.append(_check(
            "agents.negotiation_t_extension",
            SandboxCheckStatus.PASS,
            _message(lang, "agents.negotiation_t_extension.detail_pass"),
        ))

    return checks


def validate_sandbox_static(
    psop: PSOP,
    agent_cards: Iterable[Any] | None = None,
    lang: str = "zh",
) -> SandboxStaticReport:
    """Validate workflow structure and referenced AgentCard capabilities."""
    checks, dag_summary = _structure_checks(psop, lang)
    if agent_cards is not None:
        checks.extend(_agent_checks(psop, agent_cards, lang))

    if any(check.status == SandboxCheckStatus.FAIL for check in checks):
        verdict = SandboxCheckStatus.FAIL
    elif any(check.status == SandboxCheckStatus.WARNING for check in checks):
        verdict = SandboxCheckStatus.WARNING
    else:
        verdict = SandboxCheckStatus.PASS

    return SandboxStaticReport(
        workflow_id=psop.id,
        workflow_name=psop.name,
        verdict=verdict,
        checks=checks,
        dag_summary=dag_summary,
    )

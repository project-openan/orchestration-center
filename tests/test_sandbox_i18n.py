from types import SimpleNamespace

from orchestrate.core.model.psop import PSOP, JumpCondition, Step, Task
from orchestrate.sandbox.i18n import translate
from orchestrate.sandbox.stub_runtime import StubAgentRuntime
from orchestrate.validation.sandbox_validator import validate_sandbox_static


def _flatten(value, prefix=""):
    result = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def test_locale_resources_have_the_same_keys():
    from orchestrate.sandbox import i18n

    en = _flatten(i18n._load_language("en"))
    zh = _flatten(i18n._load_language("zh"))

    assert set(en) == set(zh)


def test_translate_interpolates_and_falls_back_to_english():
    assert translate("zh-CN", "checks.structure.cycle.detail_fail", path="a -> b") == "检测到循环依赖：a -> b"
    assert translate("zh-CN", "not.existing.key") == "not.existing.key"


def test_default_validator_messages_use_zh_resources():
    psop = PSOP(
        name="flow",
        steps=[
            Step(name="a", subtasks=[Task(description="task", agent="agent-a", skill="skill-a")]),
            Step(name="b", subtasks=[Task(description="task", agent="agent-a", skill="skill-a")], context_from=["missing"]),
        ],
    )
    card = SimpleNamespace(name="agent-a")
    report = validate_sandbox_static(psop, [card], lang="zh")

    check = next(item for item in report.checks if item.check_id == "structure.context_sources")
    assert any("上下文源 'missing' 不存在" in issue for issue in check.evidence)


def test_stub_default_response_uses_zh_resource():
    card = SimpleNamespace(
        name="agent-a",
        description="SPN diagnosis",
        skills=[SimpleNamespace(id="skill-a", name="skill-a", description="SPN skill")],
    )
    runtime = StubAgentRuntime([card], lang="zh")
    response = runtime._default_response(SimpleNamespace(agent_name="agent-a", skill="skill-a"))

    assert response.startswith("[Stub 响应]")
    assert "SPN skill" in response

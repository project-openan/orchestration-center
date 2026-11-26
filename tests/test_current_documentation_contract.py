# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Public onboarding must agree with the enforced account/bootstrap contract."""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Directories that never hold shipped documentation; used only by the git-less fallback.
_SKIP_DIRECTORIES = {"node_modules", ".venv", ".git", "data", ".pytest-tmp", ".pytest_cache",
                     "__pycache__", "dist", "build", "reviews"}
_MERMAID_FENCE = re.compile(r"^mermaid$", re.IGNORECASE)
_NEAR_MISS_FENCE = re.compile(r"^mermaid\S*", re.IGNORECASE)
_ENTITY_CODE = re.compile(r"#(?:\d+|[A-Za-z][A-Za-z0-9]*);")


def _repository_markdown():
    """Documentation that ships or is about to ship: tracked Markdown plus untracked,
    non-ignored Markdown. Gitignored local notes (reviews/, data/) never reach GitHub,
    so they must not fail this contract. Without a usable git, prune-walk instead.
    """
    try:
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.md"],
                                 capture_output=True, check=False)
        pending = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--others",
                                  "--exclude-standard", "--", "*.md"], capture_output=True, check=False)
    except OSError:
        tracked = pending = None
    if tracked is not None and tracked.returncode == 0:
        payload = tracked.stdout + (pending.stdout if pending.returncode == 0 else b"")
        return sorted(name for name in payload.decode("utf-8", "replace").split("\0") if name)
    documents = []
    for directory, subdirectories, filenames in os.walk(ROOT, onerror=lambda _error: None):
        subdirectories[:] = [name for name in subdirectories if name not in _SKIP_DIRECTORIES]
        documents += [Path(directory, name).relative_to(ROOT).as_posix()
                      for name in filenames if name.endswith(".md")]
    return sorted(documents)


def _fenced_blocks(text):
    """Yield ``(info_string, body_lines, line_of_first_body_line)`` per code fence."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opening = re.match(r"^(?P<fence>`{3,}|~{3,})(?P<info>.*)$", lines[index])
        if opening is None:
            index += 1
            continue
        fence, info = opening.group("fence"), opening.group("info").strip()
        closing = re.compile(r"^" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
        index += 1
        start = index
        while index < len(lines) and not closing.match(lines[index]):
            index += 1
        yield info, lines[start:index], start + 1
        index += 1


MARKDOWN = _repository_markdown()


def test_markdown_inventory_is_discoverable():
    assert len(MARKDOWN) > 5, f"documentation inventory looks wrong: {MARKDOWN}"


@pytest.mark.parametrize("relative", ["README.md", "README_zh.md", "docs/DESIGN.md"])
def test_public_documents_keep_their_sequence_diagrams(relative):
    """The published workflow walkthroughs stay diagrammed, not prose-only."""
    diagrams = [body for info, body, _ in _fenced_blocks((ROOT / relative).read_text(encoding="utf-8"))
                if _MERMAID_FENCE.match(info)]
    assert diagrams, f"No Mermaid diagram left in {relative}"
    assert any(next((row.strip() for row in body if row.strip()), "").lower() == "sequencediagram"
               for body in diagrams), f"No sequenceDiagram left in {relative}"


@pytest.mark.parametrize("relative", MARKDOWN)
def test_mermaid_fences_use_the_exact_language_identifier(relative):
    """GitHub renders a diagram only when the fence language is exactly 'mermaid'."""
    text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
    for info, _body, line in _fenced_blocks(text):
        if _NEAR_MISS_FENCE.match(info) and not _MERMAID_FENCE.match(info):
            pytest.fail(f"{relative}:{line}: write the fence as ```mermaid, found {info!r}")


@pytest.mark.parametrize("relative", MARKDOWN)
def test_sequence_diagrams_never_contain_a_raw_semicolon(relative):
    """A raw ASCII semicolon ends a Mermaid statement in *every* sequence-diagram
    position: a Note, a message text, a participant alias, an alt/loop label and a
    title each abort the whole diagram on GitHub with "Parse error ... Expecting ...".
    The entity code #59; keeps the literal character. ``flowchart`` and
    ``stateDiagram-v2`` labels tolerate a raw semicolon (checked against Mermaid's
    own parser), so they are deliberately left unrestricted here. A ``%%`` line is
    a comment and is skipped, but an inline ``%%`` is *not*: it stays part of the
    statement, so a semicolon after it still ends the diagram.
    """
    text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
    for info, body, line in _fenced_blocks(text):
        if not _MERMAID_FENCE.match(info):
            continue
        head = next((row.strip() for row in body if row.strip()), "")
        if head.lower() != "sequencediagram":
            continue
        for offset, row in enumerate(body):
            if row.lstrip().startswith("%%"):
                continue
            statement = _ENTITY_CODE.sub("", row)
            assert ";" not in statement, (
                f"{relative}:{line + offset}: a raw ';' ends the Mermaid statement; "
                f"escape it as #59;: {row.strip()}"
            )


@pytest.mark.parametrize("relative, marker", [
    ("docs/en/Orchestration Center API Reference.md", "does not generate"),
    ("docs/zh/编排中心API参考.md", "不会自动生成"),
])
def test_intent_execution_documents_no_match_failure_not_automatic_generation(relative, marker):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert marker in text
    assert "No matching workflow found" in text
    assert "auto-generates if no match" not in text
    assert "无匹配则自动生成" not in text


def test_execute_request_schema_does_not_promise_generation_or_effective_name():
    from orchestrate.server.external_api import ExecuteRequest, execute_workflow

    import inspect

    schema = ExecuteRequest.model_json_schema()["properties"]
    assert "does not generate" in schema["task"]["description"]
    assert schema["name"]["deprecated"] is True
    assert "ignored" in schema["name"]["description"]
    assert "auto-generate" not in inspect.getdoc(execute_workflow)


@pytest.mark.parametrize("relative", [
    "docs/en/Orchestration Center User Guide.md", "docs/zh/用户指南.md",
    "docs/en/Orchestration Center Development Guide.md", "docs/zh/开发指南.md",
    "docs/en/Orchestration Center API Reference.md", "docs/zh/编排中心API参考.md",
    "docs/en/MySQL Persistence.md", "docs/zh/MySQL持久化配置.md",
])
def test_current_guides_do_not_promise_default_password_or_anonymous_mode(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "OpenAN@2026" not in text
    assert "OC_ADMIN_INITIAL_PASSWORD" in text
    assert "No Security" not in text
    assert "所有 API 接口开放访问" not in text
    assert "authentication is disabled (backward compatible)" not in text


@pytest.mark.parametrize("relative", [
    "docs/en/Orchestration Center API Reference.md", "docs/zh/编排中心API参考.md"
])
def test_sandbox_paths_are_complete_and_unambiguous(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "`/orchestrate/sandbox/" not in text
    assert "`/rest/v1/orchestrate/sandbox/" in text


def test_legacy_gcp_guard_precedes_side_effects():
    text = (ROOT / "deploy-all.ps1").read_text(encoding="utf-8")
    assert text.index('throw "Legacy GCP') < text.index("Remove-Item")
    assert text.index('throw "Legacy GCP') < text.index("Get-Command gcloud")


@pytest.mark.parametrize("relative", [
    "README.md", "README_zh.md", "docs/DESIGN.md",
    "docs/en/Orchestration Center API Reference.md", "docs/zh/编排中心API参考.md",
])
def test_public_event_contract_does_not_invent_init_or_named_close(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert '"type":"init"' not in text
    assert '"type": "init"' not in text
    assert "cancelled" in text


@pytest.mark.parametrize("relative", ["docs/zh/用户指南.md", "docs/zh/编排中心API参考.md"])
def test_pdf_input_heading_is_not_translated(relative):
    from orchestrate.solution_package.parse_flow import SolutionPackageParser
    assert SolutionPackageParser.select_chapter_title(['6. Interaction Flow'], '5. Interaction Flow') == '6. Interaction Flow'
    assert "5. Interaction Flow" in (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", [
    "docs/en/Orchestration Center API Reference.md", "docs/zh/编排中心API参考.md",
])
@pytest.mark.parametrize("outcome", ["complete", "cancelled", None])
def test_documented_sse_parser_handles_heartbeat_unknown_events_and_cancellation(relative, outcome, monkeypatch):
    import requests

    text = (ROOT / relative).read_text(encoding="utf-8")
    start = text.index("import json\nimport os\nfrom urllib.parse import quote")
    snippet = text[start:text.index("\n```", start)]
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_lines(self, **kwargs):
            yield ": heartbeat"
            yield ""
            yield 'data: {"type":"future_extension","message":"optional payload"}'
            if outcome is not None:
                yield 'data: {"type":"' + outcome + '"}'

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setenv("OC_TOKEN", "test-only-token")
    monkeypatch.setenv("PSOP_ID", "test id")
    monkeypatch.delenv("OC_BASE_URL", raising=False)
    monkeypatch.setattr(requests, "get", get)
    scope = {}
    if outcome is None:
        with pytest.raises(RuntimeError):
            exec(compile(snippet, relative, "exec"), scope)
        assert scope["terminal"] is False
    else:
        exec(compile(snippet, relative, "exec"), scope)
        assert scope["terminal"] is True
    assert calls[0][0].endswith("/test%20id?lang=zh")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-only-token"
    assert "verify" not in calls[0][1]  # requests' secure default is preserved.

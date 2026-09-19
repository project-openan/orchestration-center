from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_orchestration_runtime_does_not_import_samples():
    violations = []
    for path in (ROOT / "orchestrate").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "from samples" in text or "import samples" in text:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_host_agent_runtime_does_not_import_orchestration_center():
    violations = []
    for path in (ROOT / "host_agent").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "from orchestrate" in text or "import orchestrate" in text:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []

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

import ast
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


@pytest.mark.parametrize("source,forbidden", [
    ("common", ("orchestrate", "host_agent", "samples")),
    ("orchestrate/runtime", ("orchestrate.server",)),
])
def test_architecture_import_direction(source, forbidden):
    violations = [
        f"{path.relative_to(ROOT)}: {module}"
        for path in (ROOT / source).rglob("*.py")
        for module in _imports(path)
        if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
    ]
    assert violations == []


def _run_cold_import(code):
    # A separate interpreter prevents earlier pytest imports from registering
    # handlers or masking a transitive package dependency.
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT,
        env={**os.environ, "PYTEST_RUNNING": "1"}, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_common_custom_cold_import_does_not_load_application():
    _run_cold_import("""
        import sys
        import common.custom
        from common.custom.default_handle import HandlerRegistry
        assert HandlerRegistry._defaults == {}
        assert HandlerRegistry._overrides == {}
        assert not any(
            name.split('.')[0] in {'orchestrate', 'host_agent', 'samples'}
            for name in sys.modules
        )
    """)


def test_runtime_cold_import_does_not_load_server():
    _run_cold_import("""
        import sys
        import orchestrate.runtime.exec_engine
        from orchestrate.core.shared_handlers import SharedHandlers
        assert not any(
            name == 'orchestrate.server' or name.startswith('orchestrate.server.')
            for name in sys.modules
        )
    """)


@pytest.mark.parametrize("mode", ["file", "postgresql"])
@pytest.mark.parametrize("entrypoint", [
    "import orchestrate.handlers",
    "from orchestrate.core.shared_handlers import SharedHandlers",
])
def test_business_registration_cold_start_routes_every_interface(mode, entrypoint):
    _run_cold_import(f"""
        from common.util import config_util
        config_util.get_conf = lambda: {{'persistence_mode': {mode!r}}}
        from common.custom.default_handle import HandlerRegistry
        from common.custom.interface_type import InterfaceType
        assert HandlerRegistry._defaults == {{}}
        assert HandlerRegistry._overrides == {{}}
        {entrypoint}
        from orchestrate.handlers import db_handlers, file_handlers
        expected = {{
            InterfaceType.SAVE_PSOP: file_handlers.SavePsopHandler,
            InterfaceType.GET_ALL_PSOP: file_handlers.GetAllPsopsHandler,
            InterfaceType.GET_PSOP_BY_ID: file_handlers.GetPsopHandler,
            InterfaceType.DELETE_PSOP: file_handlers.DeletePsopHandler,
            InterfaceType.SAVE_EXECUTION_RECORD: file_handlers.SaveExecutionRecordHandler,
            InterfaceType.LIST_EXECUTION_RECORDS: file_handlers.ListExecutionRecordsHandler,
            InterfaceType.GET_EXECUTION_RECORD: file_handlers.GetExecutionRecordHandler,
            InterfaceType.DELETE_EXECUTION_RECORD: file_handlers.DeleteExecutionRecordHandler,
        }}
        assert set(expected) == set(InterfaceType) - {{InterfaceType.AUTHENTICATE_EXTERNAL}}
        assert set(HandlerRegistry._defaults) == {{item.value for item in expected}}
        assert set(HandlerRegistry._overrides) == set(HandlerRegistry._defaults)
        for interface, file_class in expected.items():
            wanted = (file_class if {mode!r} == 'file'
                      else getattr(db_handlers, 'Custom' + file_class.__name__))
            assert type(HandlerRegistry.get_handler(interface)) is wanted, interface
    """)


def test_orchestration_runtime_does_not_import_samples():
    violations = []
    for path in (ROOT / "orchestrate").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "from samples" in text or "import samples" in text:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_host_agent_runtime_does_not_import_application_or_sample_packages():
    violations = []
    for path in (ROOT / "host_agent").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        forbidden = ("from orchestrate", "import orchestrate", "from samples", "import samples", "from common", "import common")
        if any(marker in text for marker in forbidden):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_host_agent_runtime_contains_no_demo_credentials():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "host_agent").rglob("*.py")
        if "__pycache__" not in path.parts
    )

    assert "Admin@123" not in text

# AGENTS.md

## Project overview

A2A-T Multi-Agent Orchestration Center — visual workflow designer + execution engine for multi-agent collaboration via the A2A protocol.

| Layer | Stack |
|---|---|
| Backend | Python 3, FastAPI, uvicorn, loguru |
| Frontend | Node.js, React 18, Vite, Tailwind CSS, React Flow |
| Agent protocol | a2a-t-sdk (negotiation), a2a-sdk (http-server + grpc) |
| Storage | File-based JSON (`data/workflow_storage/`) or PostgreSQL |

## Quick start

```powershell
# Create venv (once)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Start backend (port 5001)
python -m orchestrate.start

# Start frontend (port 3003, from workflow-designer/)
cd workflow-designer; npm install; npm run dev

# Start sample agents (required for execution)
python -m samples.start_agents_server
```

## How to run tests

**No `pytest.ini`, `conftest.py`, or `tox.ini` exists.** Two separate test directories:

```powershell
# Unit / module tests (12 files)
pytest test/test_exec_engine.py -v
pytest test/ -v

# Integration tests — require a running backend, do real HTTP calls
pytest tests/test_external_apis.py -v -s
```

**Run a single test:**

```powershell
pytest test/test_exec_engine.py::TestDynamicWorkflowEngine::test_linear_execution -v
```

## Architecture notes

### Entrypoints (all run via `-m`)

- `python -m orchestrate.start` — backend server
- `python -m samples.start_agents_server` — 8 sample A2A agents

### Two API layers in one FastAPI app

- **Internal** — `/rest/v1/orchestrate/*` — consumed by the React frontend
- **External** — `/api/v1/*` — public-facing API
- Legacy routes for backward-compatible redirects also exist

### Config system (non-standard)

Config is loaded by `common/util/config_util.py:get_conf()`. It reads `etc/conf/server.conf` then `etc/conf/server.properties` (second file overrides), parsing `key=value` lines. **All keys are lowercased**. No env-var or structured-config library is used.

Key config keys: `ip`, `port`, `enable_https`, `persistence_mode`, `agent_registry_url`, `forwarded_allow_ips`.

### Persistence mode

`persistence_mode=file` (default) → file-based JSON storage under `data/workflow_storage/`.
`persistence_mode=postgresql` → auto-creates DB tables on startup via `database/utils/table_creation.py`, reads connection from `etc/conf/db_config.json`.

The `WorkflowStorage` singleton is accessed via `get_workflow_storage()` (uses `@lru_cache(maxsize=1)`).

### A2A-T SDK config

`.env` for the a2a-t-sdk is auto-generated from `common/config/llm_config.json` via `common/a2at_config.py`.

## Repo layout (what matters)

```text
orchestrate/           # Core backend: models, runtime engine, server, registry client
  core/model/          # PSOP, PreFlow, ExecutionRecord (Pydantic)
  core/psop_generator.py   # LLM-driven PreFlow → PSOP
  runtime/exec_engine.py   # DynamicWorkflowEngine
  server/frontend_support_server.py  # FastAPI app & internal API
  server/external_api.py             # External API routes
common/                # Shared infra: config, LLM, logging, certs, util
  custom/              # Pluggable handler pattern (HandlerRegistry)
  llm/                 # LLM abstraction (generic HTTP client + auth strategies)
workflow-designer/     # React frontend (separate Node project)
samples/               # Sample A2A agents + start script
database/              # PostgreSQL support (optional)
etc/conf/              # server.conf, server.properties, db_config.json
test/                  # Unit/module tests (pytest, 12 files)
tests/                 # Integration tests (1 file, requires running server)
data/workflow_storage/ # File-based persistence (PSOP, PreFlow, execution records)
```

## Conventions & gotchas

- **Two test dirs**: `test/` (unit) vs `tests/` (integration, needs live server). No shared fixtures or conftest.
- **No Python lint, typecheck, or formatter config** exists.
- **Frontend is JS/JSX, not TypeScript**.
- **All Python code is run as modules** (`python -m`, not `python file.py`). Imports use absolute paths rooted at repo root.
- **Sample agents must be running** for workflow execution to succeed (they provide the actual A2A agent endpoints).
- **Workflow designer expects backend at `http://127.0.0.1:5001`** (hardcoded in `workflow-designer/src/service/api.js`).
- **CI/CD** configured in `.github/workflows/ci.yml` — runs pytest (unit) and ESLint (frontend).
- **License headers required** on all source files (Apache 2.0, Huawei copyright).

## Merge workflow (GitCode)

**IMPORTANT: Always follow this merge principle:**

1. **Commit to fork first** — All changes must be committed to the personal fork (`guofei6_/orchestration-center`) before creating a PR.
2. **Create PR to upstream** — Submit PR from fork to upstream (`OpenAN/orchestration-center`).
3. **Never push directly to upstream** — Always use the fork → PR → merge workflow.

**Local-only files (do NOT commit):**
- `workflow-designer/src/service/api.js` — Contains local debug configuration (API endpoint). Keep local modifications for development, do not include in commits.
- `etc/conf/server.conf` — Local server configuration. Revert any local changes before committing.

## Key commands reference

```powershell
# Backend
python -m orchestrate.start              # Start server (HTTP on :5001)
python -m samples.start_agents_server    # Start sample agents

# Frontend (cd workflow-designer)
npm run dev        # Vite dev server (:3003)
npm run build      # Production build
npm run lint       # ESLint
npm run coverage   # Vitest + coverage
```

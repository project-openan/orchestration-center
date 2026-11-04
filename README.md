<!--
Copyright (c) 2026 Huawei Technologies Co., Ltd.
All Rights Reserved.

SPDX-License-Identifier: Apache-2.0

   Licensed under the Apache License, Version 2.0 (the "License"); you may
   not use this file except in compliance with the License. You may obtain
   a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
   License for the specific language governing permissions and limitations
   under the License.
-->

# A2A-T Multi-Agent Orchestration Center

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-20.19+-green.svg" alt="Node.js"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-orange.svg" alt="License"></a>
</p>

<p align="center">
  <strong>A visual orchestration platform for multi-agent collaboration via the A2A-T protocol.</strong>
  <br>
  基于 A2A-T 协议的多智能体可视化编排平台。
</p>

<p align="center">
  <a href="./README_zh.md">中文</a>
</p>

---

## Overview

The Orchestration Center is a visual platform for designing and executing multi-agent workflows. It provides a **drag-and-drop workflow designer**, an **async execution engine**, and **A2A-T negotiation** integration — enabling teams to build, manage, and run complex agent collaboration flows without writing code.

**Use cases:** Telecom network assurance workflows, RAN energy-saving orchestration, SPN fault handling pipelines, enterprise multi-agent automation.

```mermaid
sequenceDiagram
    actor User as User
    participant FE as Workflow Designer<br/>(React :3003)
    participant BE as Backend :5001<br/>(FastAPI)
    participant LLM as LLM
    participant Reg as Agent Registry
    participant Host as Host Agent runtime
    participant Agt as A2A Agents

    rect rgb(240, 248, 255)
        Note over User, Reg: 1. Agent Discovery
        FE->>+BE: GET /rest/v1/orchestrate/agent-cards
        BE->>Reg: Fetch AgentCards
        Reg-->>BE: AgentCard[]
        BE-->>-FE: agent-cards JSON
        FE-->>User: Display agent catalog
    end

    rect rgb(255, 250, 240)
        Note over User, Reg: 2. Workflow Creation (3 modes)
        alt 2a. PDF Import
            User->>FE: Upload PDF
            FE->>+BE: POST /rest/v1/orchestrate/parse-pdf
            BE->>LLM: Parse chapters & tasks
            LLM-->>BE: Structured preflow
            BE-->>-FE: PreFlow JSON
            FE->>BE: POST /rest/v1/orchestrate/generate-from-preflow
            BE->>LLM: Generate PSOP from PreFlow
            LLM-->>BE: PSOP workflow
            BE-->>FE: PSOP JSON
        else 2b. Manual Drag & Drop
            User->>FE: Drag agents, connect nodes, configure
            FE->>FE: Build workflow graph (React Flow)
        else 2c. Natural Language Intent
            User->>FE: Enter intent text
            FE->>+BE: POST /rest/v1/orchestrate/generate-from-intent
            BE->>Reg: Fetch AgentCards
            Reg-->>BE: AgentCard[]
            BE->>LLM: Generate PSOP from intent
            LLM-->>BE: PSOP workflow
            BE-->>-FE: PSOP JSON
        end
    end

    rect rgb(240, 255, 240)
        Note over User, Reg: 3. Save Workflow
        User->>FE: Click Save
        FE->>+BE: POST /rest/v1/orchestrate/workflows<br/>{psop: {...}}
        BE->>BE: Validate PSOP (Pydantic)
        BE->>BE: Persist (File JSON / PostgreSQL / MySQL)
        BE-->>-FE: {workflow_id: "..."}
        FE-->>User: Saved successfully
    end

    rect rgb(255, 245, 255)
        Note over User, Agt: 4. Execute Workflow
        User->>FE: Click Execute
        FE->>+BE: GET /rest/v1/orchestrate/execute<br/>?psop_id=xxx&user_intent=...&lang=zh
        BE->>Reg: Fetch AgentCards
        Reg-->>BE: AgentCard[]
        BE->>BE: Capture selected PSOP snapshot
        BE->>Host: A2A-T intent + PSOP ID + snapshot
        Note over Host: Validate snapshot#59; SDK schedules its DAG (no new search)
        loop Workflow steps and tasks
            Host->>Agt: A2A/A2A-T task or negotiation
            Agt-->>Host: Results and status
            Host-->>BE: TaskUpdate metadata.__sdk_event__
            BE-->>FE: SSE data: SDK event
        end
        BE->>BE: Store bounded event tail and final status
        BE-->>FE: complete/error/cancelled or abnormal EOF
        BE-->>-FE: Stream EOF (no guaranteed close event)
        FE-->>User: Execution finished
    end
```

## Features

| Category | Capability |
|----------|------------|
| **Visual Designer** | React Flow-based drag-and-drop workflow builder with automatic Dagre layout |
| **Multi-Mode Creation** | PDF document import, manual drag-and-drop, and natural-language-to-workflow via LLM |
| **A2A-T Negotiation** | Workflow-engine coordinates task identity and exchange lifecycle; host callbacks use current A2A-T content generation and validation APIs |
| **Execution Engine** | `OrchestrationEngine` — thin A2A-T dispatch channel; PSOP workflow execution delegated to the Host Agent via workflow-engine SDK |
| **Semantic Search** | Natural-language retrieval of previously built workflows |
| **Dual API Layer** | Internal API (`/rest/v1/orchestrate/*`) for the frontend + External API (`/api/v1/*`) for third-party integration |
| **SSE Streaming** | Execution phases, SDK task/step/agent events and complete/error/cancelled results; see the API event contract |
| **Pluggable Storage** | File-based JSON, PostgreSQL or MySQL persistence via HandlerRegistry |
| **Template Marketplace** | Bundled cross-city SPN diagnosis template; add reviewed templates under samples/workflow_templates/ |
| **Sample Agents** | 3 sample A2A agents (Host Agent + two SPN domain agents) for testing and demonstration |

MySQL setup, storage boundaries and container instructions: [MySQL persistence](docs/en/MySQL%20Persistence.md).

SPG batch import, default-library readiness and safe upgrade of installed examples: [SPG import](docs/en/SPG%20Import.md). Default AN L4 AgentCards are a planning catalog, not deployed business agents.

PSOP intent retrieval, the optional embedding recall switch and how it degrades: [PSOP retrieval](docs/en/PSOP%20Retrieval.md).

## Quick Start

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| Python | 3.12+ |
| Node.js | 20.19+ |

### Install & Run

```bash
# Clone the repository
git clone https://github.com/project-openan/orchestration-center.git
cd orchestration-center

# Backend setup
python3 -m venv .venv
source .venv/bin/activate      # Linux
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt

# Provision configuration only if server.conf does not already exist.
# Copy etc/conf/server.conf.example to etc/conf/server.conf; never overwrite local configuration.
# Copy etc/config/models.yaml.example to etc/config/models.yaml, set model/url and supply named secrets in .env.
# Configure the login account before startup, including local demos.
python generate_access_password.py      # prints a hash; copy it into access_password manually

# Start backend (port 5001)
python -m orchestrate.start

# Frontend setup (separate terminal)
cd workflow-designer
npm install --force
npm run dev                     # port 3003

# (Optional) Start sample agents
cd ..
python -m samples.start_agents_server
```

### Verify

| Service | Check |
|---------|-------|
| Backend | `Uvicorn running on http://127.0.0.1:5001` |
| Frontend | Open `http://localhost:3003` in browser |
| Sample Agents | Agent startup messages in console |

## Docker Deployment

The root Compose files are a local deployment baseline, not an unattended production installer.
Start the [registry center](https://github.com/project-openan/registry-center) on the shared
`openan-net` network first, or configure a reachable `AGENT_REGISTRY_URL`.

Before `docker compose up -d --build`:

1. Create `openan-net` if it does not exist: `docker network create openan-net`.
2. Supply `ORCH_ACCESS_PASSWORD` (the hash printed by `generate_access_password.py`) through a
   protected deployment environment. Never put a password/hash in an image or commit a real `.env`.
3. Prepare `etc/config/models.yaml` and its named environment secrets; set `LLM_CONFIG_HOST_FILE`
   if using a different host file. Configure the registry's independent access Token where required.
4. Review every environment default, port binding and volume permission before exposing the stack.

The base Compose backend uses HTTP by default (`ORCH_ENABLE_HTTPS=false`), and its default registry
URL is `http://openan-registry-center:5000`. These are explicit Compose overrides, not universal
service defaults. The frontend is served at `http://localhost:3003` and proxies same-origin
`/api/orchestrate/` requests; internal browser APIs use login sessions, public `/api/v1/*` uses Bearer.

For HTTPS, prepare TLS/CA materials, matching SANs and client certificates when mTLS is enabled;
configure backend, proxy, probe and outbound registry TLS separately. Skipping peer verification
does not remove login or registry authentication. Follow the [transport contract](docs/transport-runtime.md)
and [MySQL/container guide](docs/en/MySQL%20Persistence.md); the root file alone is not production acceptance.

The development overlay starts sample agents:

```bash
docker compose -f docker-compose.yml -f docker-compose-dev.yml up -d --build
```

The overlay currently mounts a legacy model location. Explicitly set `LLM_CONFIG_HOST_FILE` to your
prepared canonical YAML file so the host source is an existing file, not a newly created directory.
Sample endpoints advertise `SAMPLE_AGENTS_HOST=sample-agents`; do not simultaneously register a
host-run sample process against the same registry. Samples are demonstrations, not production agents.
Successful container startup does not prove real model reachability or workflow execution.

## Architecture

```mermaid
flowchart TB
    subgraph frontend["Frontend"]
        wd["Workflow Designer<br/>React 18 + Vite + Tailwind<br/>Port 3003"]
    end

    subgraph backend["Orchestration Backend (Port 5001)"]
        direction TB
        api["Dual API Layer<br/>Internal /rest/v1/orchestrate/*<br/>External /api/v1/*"]
        domain["Core Domain<br/>PSOP Generator · Intent Generator<br/>Semantic Search · Publisher"]
        engine["OrchestrationEngine<br/>Thin A2A-T Dispatch Channel<br/>SSE Event Forwarding"]
    end

    subgraph storage["Storage"]
        direction LR
        file[("File JSON")]
        pg[("PostgreSQL")]
    end

    subgraph agents["A2A Agents"]
        direction LR
        a1["Agent A"]
        a2["Agent B"]
        a3["Agent C..."]
    end

    wd -->|"REST / SSE"| api
    api --> domain
    domain --> engine
    engine --> file
    engine --> pg
    engine -->|"A2A-T Protocol"| wb["Host Agent<br/>(Leader · workflow-engine SDK)"]
    wb -->|"A2A Protocol<br/>+ A2A-T Negotiation"| a1
    wb --> a2
    wb --> a3

    style backend fill:#e1f5fe,stroke:#0288d1
    style frontend fill:#e8f5e9,stroke:#388e3c
    style storage fill:#f3e5f5,stroke:#7b1fa2
    style agents fill:#fff3e0,stroke:#f57c00
```

## API Overview

### External API (`/api/v1/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/orchestrate/sop` | SOP-based workflow orchestration (JSON text or file upload) |
| `POST` | `/api/v1/orchestrate/intent` | Intent-based workflow orchestration |
| `GET` | `/api/v1/orchestrate/psop/{id}` | Get PSOP workflow detail |
| `POST` | `/api/v1/orchestrate/search` | Search workflows by natural language intent |
| `POST` | `/api/v1/orchestrate/execute` | Auto-orchestrate + execute (SSE streaming) |
| `GET` | `/api/v1/orchestrate/execute/{id}` | Execute a known PSOP (SSE streaming) |
| `GET` | `/api/v1/executions` | List execution records |
| `GET` | `/api/v1/executions/{id}` | Get execution result |

### Internal API (`/rest/v1/orchestrate/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/workflows` | List workflows |
| `GET` | `/workflows/{id}` | Get workflow detail |
| `POST` | `/workflows` | Create workflow |
| `DELETE` | `/workflows/{id}` | Delete workflow |
| `POST` | `/parse-pdf` | Parse PDF SolutionPackage and extract PreFlow |
| `POST` | `/generate-from-preflow` | Generate PSOP from PreFlow |
| `POST` | `/generate-from-intent` | Generate PSOP from intent |
| `POST` | `/retrieve-by-intent` | Retrieve workflow by intent |
| `POST` | `/retrieve-topn-by-intent` | Retrieve top-N workflows by intent |
| `GET` | `/agent-cards` | List available agent cards |
| `GET` | `/solution-packages` / `/solution-packages/{pdf_filename}` | List/get a solution package |
| `DELETE` | `/solution-packages/{pdf_filename}` | Remove one package, not all packages |
| `PUT` / `DELETE` | `/agent-cards/{organization}/{name}` | Admin-only card proxy |
| `GET` | `/dispatch` | intent + agent_name, optional lang; SSE |
| `GET` | `/templates` | List workflow templates |
| `POST` | `/templates/{id}/import` | Import workflow from template |
| `GET` | `/execute` | Start workflow execution (SSE). Query params: `psop_id`, `user_intent`, `lang` |
| `GET` | `/execution-records` | List execution records |
| `GET` | `/execution-records/{id}` | Get execution record detail |
| `DELETE` | `/execution-records/{id}` | Delete execution record |
| `POST` | `/sandbox/{workflow_id}/run` | Start an internal sandbox verification |
| `GET` | `/sandbox/verifications` | List sandbox reports |
| `GET` | `/sandbox/verifications/{id}` | Get sandbox status or report |
| `GET` | `/sandbox/verifications/{id}/events` | Get sandbox execution events |
| `DELETE` | `/sandbox/verifications/{id}` | Cancel a run or delete its report |
| `GET` | `/sandbox/templates/{workflow_id}` | Get sandbox stub templates |
| `PUT` | `/sandbox/templates/{workflow_id}` | Save sandbox stub templates |

Full API specification: [API Reference](docs/en/Orchestration%20Center%20API%20Reference.md)

Execute-by-ID forwards the selected PSOP ID and a detached snapshot to the Host Agent without another intent search. `user_intent` supplies execution context, not workflow selection. Later workflow edits apply to subsequent executions, not the captured snapshot. See API section 5.

### Host Agent Runtime

`host_agent` provides the workflow execution host. It runs as an independent A2A Agent process, invokes the Workflow Engine, wraps execution events, and manages the process lifecycle. Business decisions are injected through ControlPoint implementations; the sample SPN policy is provided by `samples/spn_host_agent`. Start it with:

```bash
python -m samples.start_agents_server
```

The Orchestration Center owns persisted PSOP data. When the UI dispatches a workflow, it passes a PSOP snapshot to the Host Agent in A2A metadata; direct intent execution falls back to the configured workflow repository.

### Sandbox Verification

Sandbox verification is separate from formal execution:

1. **Static checks** validate DAG structure, `context_from` ancestry, Agent/Skill matching, and Task-T/Negotiation-T declarations.
2. **Stub execution** runs the real Workflow Engine scheduling path but replaces remote A2A calls with locally generated Stub responses.
3. **Reports** record pass/warning/fail checks, execution path, context trace, Stub interactions, risks, and suggestions.
4. **Editor snapshots** allow unsaved or imported workflows to be verified. A valid `psop` snapshot in the run request takes precedence over loading the workflow by ID.
5. **Report language** follows the `zh` / `en` run request. Backend report text is loaded from `orchestrate/sandbox/locales`.

A sandbox `pass` means workflow structure and engine scheduling were verified with Stub Agents. It does **not** prove that real Agents will produce correct business output.

## Security

The Orchestration Center provides multi-layer access control:

### Frontend Login (Internal API)

The internal API (`/rest/v1/orchestrate/*`) is protected by token-based authentication. Two modes are supported depending on `persistence_mode`:

**Database mode (`persistence_mode=postgresql` or `mysql`)**:

- The plaintext password is sent to the backend over TLS and stored using versioned bcrypt hashes; legacy hashes are upgraded on successful login.
- On an empty SQL user store, set `OC_ADMIN_INITIAL_PASSWORD` or `admin_initial_password_file` to create the first `admin`. No compiled-in password is used; existing users are never reset on restart.
- Self-registration is disabled by default; explicitly set `auth.register.enabled=true` to enable it.
- Passwords must be at least 8 characters and include at least two of: a digit, an uppercase letter, a lowercase letter, a special character. Enforced server-side (`common/util/password_util.validate_password_complexity`), not just in the UI.

**File mode (`persistence_mode=file`)**:
- A single password is configured via `access_password` in `server.conf`.
- Username is fixed as `admin`.
- Registration is not available.

### Fail-closed startup

Internal and public APIs share account authentication by default, independently
of TLS. Startup preflight checks that an account credential is configured before binding:

In file mode, set the login password hash with `python generate_access_password.py`
or `ORCH_ACCESS_PASSWORD`. In database mode, existing users are sufficient; for
an empty database only, provide `OC_ADMIN_INITIAL_PASSWORD` or
`admin_initial_password_file`. The initial password must meet login complexity
requirements and be changed after first login; it does not reset existing users.

Both HTTP and HTTPS require account login, including loopback deployments. No
development switch disables authentication, and `TESTING` cannot change runtime
authentication. The public template intentionally has no password; configure one
before starting. HTTP logs a plaintext-transport warning. `GET /health` remains a
public minimal liveness probe, not a readiness or business-authentication check.
Explicit legacy mTLS can serve direct integrations without an account, but does
not authorize the frontend/internal account APIs.

### Sample Agent Credentials

The bundled sample agents authenticate against **localhost-only demo endpoints** using platform factory-default credentials committed in `samples/agent_credentials.json`. This file exists so the demo topology works out of the box; it is read by the sample agents, not by the orchestration backend.

For anything beyond the local demo, do not reuse these defaults:
- Point the process at an external, protected credentials file via the `ORCH_AGENT_CREDENTIALS_FILE` environment variable (or the `agent_credentials_file` config key), or
- Keep the file layout but store encrypted values: any value prefixed with `enc:` is decrypted with the AES-GCM key in `A2AT_CRED_KEY` (provided by the workflow-engine SDK's credential crypto).

| Config Key | Description | Default |
|------------|-------------|---------|
| `access_password` | Versioned password hash (legacy SHA-256 supported) for file mode. Empty means account authentication is unconfigured, not disabled; default startup refuses it on HTTP and HTTPS — see [Fail-closed startup](#fail-closed-startup). | empty (unconfigured) |
| `access_token_ttl` | Session token lifetime in seconds. | `43200` (12h) |
| `persistence_mode` | `postgresql` or `mysql` enables database-backed user management; `file` uses config-based auth. | `file` |

The frontend sends the password as-is; the backend verifies its stored hash. Use a public HTTPS endpoint for confidentiality in transit. Login sets an `HttpOnly`, `SameSite=Lax` cookie; `Secure` follows `public_scheme` or the trusted request scheme, not backend TLS alone. Browser JavaScript cannot read it, and EventSource/SSE uses it without putting credentials in URLs. Explicit Bearer headers are also accepted by the internal API and take precedence over cookies.

A cookie only attaches to a **same-origin** request. Both shipped serving paths -- nginx in front of both in docker-compose, and the Vite dev server's own `/api/orchestrate` proxy for `npm run dev` -- put the frontend and this API on the same origin, so this is transparent. A manually-configured direct-IP deployment (frontend and backend on genuinely different origins) needs `CORS_ORIGINS` set to the frontend's exact origin (not the default `*`, which can't be combined with credentialed requests) for the cookie to work cross-origin at all.

> **Session storage is single-process only.** Tokens live in an in-memory dict inside the running Python process. Running with multiple `uvicorn` workers, or multiple replicas behind a load balancer, will intermittently reject valid tokens -- a token minted by one worker isn't visible to another. Every process restart also logs out all active sessions (harmless in itself given the token TTL, but worth expecting). Both bundled launch paths (`orchestrate/start.py`) run single-process today, so this doesn't bite out of the box -- but if multi-worker or multi-replica deployment is ever needed, session storage must move to a shared backend (e.g. the same PostgreSQL database, or Redis) first.

Generate the password hash (file mode):
```bash
python generate_access_password.py
```

### TLS/HTTPS

| Config Key | Description |
|------------|-------------|
| `enable_https` | Enable HTTPS for the backend server. |
| `verify_client` | Require client certificate (mTLS). Defaults to required when unset or set to anything other than the literal `false`; only an explicit `verify_client=false` in `server.conf` disables it. |
| `ssl_certfile` | Server certificate path. |
| `ssl_keyfile` | Server private key path (encrypted). |
| `ssl_ca_certs` | CA trust store for verifying client certificates. |
| `client_verify_server` | Verify remote server certs on outbound HTTPS calls (e.g., to registry center). Default `true` in the public template and main-service factories. |

Generate self-signed certificates (RSA 3072, compliant with cert validator):
```bash
python -m generate_selfsign_cert etc/ssl serverAuth
```

New TLS certificates include SANs for `DNS:localhost`, `IP:127.0.0.1` and `IP:::1` by default.
For other endpoints, repeat `--dns` / `--ip` for the actual client-facing names; explicit options replace the default SAN list:

```bash
python -m generate_selfsign_cert etc/ssl-new serverAuth --dns orch.example.test --ip 192.0.2.10
```

SANs must match the host in the client URL; IP addresses require `--ip`. Setting CN or trusting a certificate does not fix missing SANs.
Existing certificates are not updated automatically, and the tool refuses to overwrite certificates or private keys.
For an existing deployment, generate into a new directory, back up and deploy the matching certificate/key pair, then restart.
Update client trust material where required; do not overwrite the CA store used to authenticate clients.
`dataSigning` does not add TLS SANs and rejects CLI SAN options.

**Enabling HTTPS (step by step):**

1. Generate certificates (see above). For `serverAuth` the script already writes the deployment
   files expected by `server.conf` (`server.cer`, `trust.cer`, `server_key.pem`, `cert_pwd`);
   add `--plain-key` to also get the unencrypted `server_key_nopass.pem` for nginx. No manual
   copying or password file creation is needed. The fallback password path is also
   `etc/ssl/cert_pwd`. Existing raw/deployment files and client credentials are never overwritten.
   `cert_pwd` is plaintext: protect the entire directory (service-account ACLs on Windows).

2. Update `etc/conf/server.conf`:
   ```ini
   enable_https=true
   verify_client=true           # TLS client certificates required; false disables
                                 # this TLS check, not account authentication.
   agent_registry_url=https://127.0.0.1:5000   # if registry center also uses HTTPS
   ```

3. Set `client_verify_server=false` in `etc/conf/server.conf` to skip remote cert verification when connecting to other services with self-signed certs (e.g., registry center).

4. Restart the backend: `python -m orchestrate.start` (or `systemctl restart orchestration-center`)

5. If using Nginx as reverse proxy, update `proxy_pass` to `https://127.0.0.1:5001/` and add `proxy_ssl_verify off;`. Nginx needs an unencrypted private key:
   ```bash
   openssl rsa -in etc/ssl/server_key.pem -out etc/ssl/nginx_key.pem -passin pass:<your-password>
   ```
   Then in nginx.conf: `ssl_certificate_key /path/to/etc/ssl/nginx_key.pem;`

### External API Protection

Default account authentication (no mode setting required; `auto` remains an alias) uses the same accounts as frontend login. `POST /api/v1/auth/token` accepts JSON `{"username":"admin","password":"<your-password>"}` and returns `access_token`, `token_type: "Bearer"`, and `expires_in`. Use `Authorization: Bearer <access_token>` on `/api/v1/*`; cookies alone and URL tokens are rejected. `POST /api/v1/auth/logout` revokes that Bearer. Tokens share the session TTL/store; password changes and account deletion revoke all of the account's sessions. Accounts requiring an initial password change must complete it in the web UI first. Both login endpoints share per-IP brute-force limits. This is first-party login, not an OAuth2 authorization server.

HTTP and HTTPS enforce the same account authentication. `verify_client=false` or client-side `verify=False` does not bypass it. With `verify_client=true`, a TLS client certificate is additionally required. Direct legacy integrations may explicitly select `bearer` (fixed `ORCH_API_TOKEN`, at least 32 bytes), `mtls` (verified HTTPS client certificate), or `custom`; these are not automatic fallbacks. Nginx/Vite gateway requests always require the original user's Bearer for public APIs, even when the proxy itself presents a certificate. See [transport configuration](docs/transport-runtime.md).

### Auth Endpoints

The bundled Host Agent uses `HOST_ORCHESTRATION_USERNAME` and
`HOST_ORCHESTRATION_PASSWORD` to access the center's PSOP search/detail APIs through
the execution SDK. The SDK shares the acquired token across both calls and renews
it after expiry or one rejected request. Set `HOST_ORCHESTRATION_URL` when the
center is remote; use an existing account that has completed any required initial
password change. Alternatively use `HOST_ORCHESTRATION_TOKEN` for an explicitly
configured Bearer integration. Account credentials and a fixed token are mutually
exclusive. These credentials are independent of AgentCard and registry credentials.

For verified HTTPS set `client_verify_server=true`; optional
`HOST_ORCHESTRATION_CA_FILE`, `HOST_ORCHESTRATION_CLIENT_CERT`,
`HOST_ORCHESTRATION_CLIENT_KEY`, `HOST_ORCHESTRATION_CLIENT_KEY_PASSWORD` and
`HOST_ORCHESTRATION_CRL_FILE` configure the same TLS identity for login and PSOP
queries. Generic hosts can inject `OrchestrationWorkflowRepository(auth_provider=...,
...)` via `HostAgentExecutor(workflow_repository=...)`, including their existing
OAuth2 provider. With no credentials, snapshot execution is still available;
center lookups require authentication and fail with 401 when it is absent.

This integration requires `workflow-exec-engine>=0.1.1,<0.2` and
`a2a-t-sdk>=1.2.0,<2`. Until the corresponding SDK releases are published, install
the reviewed local wheels into `.venv` before installing application requirements.
An earlier 0.1.0/0.0.9 package does not contain this management-authentication API.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/token` | Same login account, returns Bearer token without setting a cookie |
| `POST` | `/api/v1/auth/logout` | Revoke the explicit account Bearer token |
| `POST` | `/rest/v1/orchestrate/auth/login` | Login with username + password, sets the session cookie |
| `POST` | `/rest/v1/orchestrate/auth/register` | Register a new user (PostgreSQL/MySQL mode only) |
| `POST` | `/rest/v1/orchestrate/auth/logout` | Revoke the session token and clear its cookie |
| `GET` | `/rest/v1/orchestrate/auth/check` | Check if auth is required, token validity, and registration availability |
| `GET` | `/rest/v1/orchestrate/auth/users` | List all users (PostgreSQL/MySQL mode only) |
| `DELETE` | `/rest/v1/orchestrate/auth/users/{username}` | Delete a user (admin cannot be deleted) |

## Configuration

| Config File | Purpose |
|-------------|---------|
| `etc/conf/server.conf` | Server IP, port, TLS certificates, persistence mode, registry URL, access password, `client_verify_server` |
| `etc/conf/server.properties` | TLS ciphers, rate limiting, connection limits |
| `etc/conf/db/postgresql.json` | PostgreSQL connection settings — gitignored; copy `etc/conf/db/postgresql.json.template` to get started (only needed for `persistence_mode=postgresql`) |
| `etc/conf/db/mysql.json` | MySQL connection settings — gitignored; copy its `.template`, inject `MYSQL_PASSWORD`, or use environment-only configuration; see [MySQL persistence](docs/en/MySQL%20Persistence.md) |
| `.env` | Local model settings and A2A-T SDK settings — gitignored; production should inject secrets through its environment |
| `etc/config/README_en.md` | LLM configuration guide |
| `generate_selfsign_cert.py` | Self-signed certificate generator (RSA 3072) |
| `workflow_engine.client.ssl_context` | Client-side SSL context factory for outbound HTTPS (provided by the workflow-engine SDK) |

## LLM configuration

Built-in `openai_compatible` (`openai` alias) and `aoc_signed` profiles supply request/response contracts.
Model definitions live in the gitignored `etc/config/models.yaml`; only
secrets come from the process environment or the repo-root `.env`:

```yaml
models:
  chat:
    provider: openai_compatible
    model: your-model
    url: https://provider.example/v1/chat/completions
    api_key_env: LLM_CHAT_API_KEY
```

```dotenv
LLM_CHAT_API_KEY=your-secret
```

The keys under `models:` are the enabled capabilities — `chat`, `embed` and
`rerank` are the built-in ones, and any other name works once a registered
profile supports it. `model` and `url` are required; `provider` defaults to
`openai`. For AOC signing set `provider: aoc_signed` and reference
`app_key_env` / `app_secret_env` under `auth:`, plus any service-specific
fields. `timeout`, `verify_ssl` and `enable_thinking` are optional. A reference
to an unset variable fails the load, and a literal secret in the file is
rejected. `LLM_CONFIG_FILE` selects a different model file, while
`docker-compose.yml` mounts one through `LLM_CONFIG_HOST_FILE`. Process
environment variables take precedence over `.env`. Changes take effect after
process restart.

Protocol contracts are registered in `common/llm/config/model_sources.py`;
adding a new model using an existing protocol needs only configuration, while
a new protocol requires a profile and its tests. `A2AT_LLM_*` remains an
independent SDK configuration.

`api_key_env` is optional for keyless local endpoints. Run
`python -m scripts.migrate_llm_config` if settings are still in `.env`, or
`python -m scripts.migrate_legacy_llm_json` if they are still in the old JSON.

This configures the orchestration backend's own LLM calls (intent parsing, PSOP retrieval, PDF
summarization). It is independent of the A2A-T negotiation SDK's configuration below.

See [`models.yaml.example`](etc/config/models.yaml.example) and
[`.env.example`](.env.example) for DeepSeek, Qwen and self-hosted-gateway examples.

## A2A-T SDK Integration

This project integrates the workflow-engine SDK for Host Agent workflow execution and agent
fulfillment negotiation. Its configuration (`A2AT_LLM_PROVIDER`, `A2AT_LLM_MODEL`,
`A2AT_LLM_API_KEY`, `A2AT_LLM_BASE_URL`, …) is read directly
from the repo-root `.env` — set it there:

```bash
A2AT_LLM_PROVIDER=openai
A2AT_LLM_MODEL=deepseek-chat
A2AT_LLM_API_KEY=<your-api-key>
A2AT_LLM_BASE_URL=https://api.deepseek.com
```

`A2AT_LLM_PROVIDER` selects the SDK's LLM client, not the model vendor — the endpoint is whatever
`A2AT_LLM_BASE_URL` points at. Keep it at `openai`: the SDK registers that name in every process,
while other names (such as `deepseek`) are registered only inside the orchestration-center backend
and make the sample agents fail with `Unknown llm provider`.

This is independent of the `LLM_CHAT_*` configuration above — there is no auto-derivation between
the two.

The workflow engine does not initialize the retired A2A-T negotiation state machine. Host code uses the current content generation and validation APIs and returns final protocol content through its callbacks.

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/en/Orchestration%20Center%20User%20Guide.md) | Features, scenarios, quick start, FAQ |
| [API Reference](docs/en/Orchestration%20Center%20API%20Reference.md) | Full REST API specification |
| [Developer Guide](docs/en/Orchestration%20Center%20Development%20Guide.md) | Custom handlers, LLM module, extension |
| [Role Binding Pilot](docs/en/Role%20Binding%20Pilot.md) | Role dispatch contract, Host validation, policy context and technical limits |
| [GCP Deployment Guide](docs/en/Orchestration%20Center%20GCP%20Containerized%20Deployment%20Guide.md) | Historical GCP guide — current one-click entrypoint is unsupported |
| [Frontend README](workflow-designer/README.md) | Workflow Designer setup and tech stack |
| [LLM Config](etc/config/README_en.md) | LLM configuration reference |

> For Chinese documentation, see [中文 README](README_zh.md) or [docs/zh/](docs/zh/).

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) for details.


数据库连接统一使用 `etc/conf/db/` 模板，密码由 `.env` / 环境变量引用；参见 [Database configuration / 数据库配置](docs/database-configuration.md)。旧连接配置不再作为运行时来源。

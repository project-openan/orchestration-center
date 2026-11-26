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

# Orchestration Center API Reference

## Before You Begin

### Introduction

  Orchestration Center is a visual orchestration platform for multi-agent collaboration, providing the following RESTful API endpoints for external system integration:

  - **SOP Orchestration**: Upload PDF/TXT/MD files or submit natural language SOP steps to automatically generate a PSOP workflow.
  - **Intent Orchestration**: Submit natural language task intent and let the LLM autonomously plan and generate a PSOP workflow.
  - **Search Workflow**: Submit natural language intent to match existing workflows in the platform, returning the most relevant TopN workflows (including ID, name, description, etc.).
  - **Search and Execute by Intent**: Submit a task description to select an existing workflow and execute it via SSE. No match does not trigger generation; the default Host reports an SSE `error`.
  - **Execute Specific Workflow**: Start execution based on a known PSOP ID, with real-time execution progress and results pushed via SSE.
  - **Query Execution Result**: Get detailed information about a workflow execution record by execution ID.

  Public integration endpoints use **`/api/v1`**. Internal browser/sandbox endpoints use **`/rest/v1/orchestrate`**; their complete paths must not be prefixed with `/api/v1`.

### Response Format

  All endpoints (except SSE streaming endpoints) return a unified JSON structure:

  | Parameter | Type    | Description                                      |
  |-----------|---------|--------------------------------------------------|
  | code      | integer | HTTP status code. 200 = success, 201 = created   |
  | message   | string  | Response message description                     |
  | status    | string  | Response status. `"success"` for success         |
  | data      | object  | Response data. See each endpoint for details     |

  Error responses have a unified format (consistent with success responses):

  | Parameter | Type    | Description                                        |
  |-----------|---------|----------------------------------------------------|
  | code      | integer | HTTP status code (e.g. 400, 404, 422, 500)         |
  | message   | string or object | Error description; role generation uses `{code, message}` |
  | status    | string  | `"error"`                                          |
  | data      | object  | `null`                                             |

### Constraints and Limitations

  - All endpoints are protected by both concurrency control (Semaphore) and token bucket rate limiting (RateLimiter). See each endpoint's constraints for details.
  - The default service port is **5001**.

### Authentication

Internal and public APIs share account authentication by default, with two account sources:

- **Database mode (PostgreSQL/MySQL)**: Users are stored in the database with versioned password hashes. User management is available; self-registration is disabled by default and requires `auth.register.enabled=true`.
- **File mode**: A single password is configured via `access_password` in `server.conf`. Username is `admin` only.

Authentication is mandatory in HTTP and HTTPS modes. File mode needs a password hash; an empty SQL user store needs `OC_ADMIN_INITIAL_PASSWORD` or `admin_initial_password_file` for first boot. Missing configuration rejects startup; account-backend failure returns 503 rather than allowing anonymous requests. Complete the initial password change in the UI and log in again before obtaining a public API token.

**Login:**
```bash
curl -X POST https://127.0.0.1:5001/rest/v1/orchestrate/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<plaintext_password>"}'
```
The password is sent in plaintext over TLS and hashed server-side. On success the session token is
set as an `HttpOnly` cookie; the response body does not contain the token itself:
```json
{"code": 200, "data": {"auth_required": true, "expires_in": 43200, "username": "admin", "role": "admin"}}
```

**Authenticated request** (the browser attaches the session cookie automatically; non-browser
clients may use the header instead):
```bash
curl -H "Authorization: Bearer <token>" https://127.0.0.1:5001/rest/v1/orchestrate/workflows
```

SSE endpoints (`EventSource`) authenticate with the same session cookie, which the browser sends
automatically. There is no query-parameter token.

Registration (PostgreSQL/MySQL mode with `auth.register.enabled=true` only):
```bash
curl -X POST https://127.0.0.1:5001/rest/v1/orchestrate/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","password":"<plaintext_password>"}'
```

**Programmatic login (same account, default `external.auth.mode=auto/user`):**

```bash
curl -X POST https://127.0.0.1:5001/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<plaintext_password>"}'
```

Successful response (no session cookie; `Cache-Control: no-store`):

```json
{"access_token":"<token>","token_type":"Bearer","expires_in":43200}
```

Pass `Authorization: Bearer <token>` to public `/api/v1/*` requests. Cookie-only
and query-token requests are rejected. POST `/api/v1/auth/logout` with that header
revokes only that token. Password changes/account deletion revoke all sessions;
tokens also expire by TTL and are lost on process restart. Initial forced password
changes must be completed via web login before API token issuance. Both login
channels share per-IP rate limits. This is not an OAuth2 authorization server.
Gateway URLs add `/api/orchestrate` before these paths and preserve the caller's
Bearer; a proxy certificate is not the caller's identity.

Account authentication is identical on HTTP and HTTPS. `verify_client=true`
additionally requires a TLS client certificate; `verify=False` at the caller does
not bypass authentication. Explicit legacy `bearer`/`mtls`/`custom` modes for direct
integrations are described in [transport configuration](../transport-runtime.md).

---

## 1. SOP Orchestration Interface

- Typical Scenario

     A user has a solution package document (PDF/TXT/MD format), or directly inputs natural language SOP step descriptions, and needs to automatically generate a multi-agent collaboration PSOP workflow.

- Description

     Accepts PDF/TXT/MD files (PDF selects "5. Interaction Flow", also accepting numbering variants such as "6. Interaction Flow"; TXT/MD reads the full content) or JSON-formatted SOP step text, and combines them with the available Agent list to generate a PSOP workflow via LLM, which is then automatically saved.

- Interface Constraints

  - File upload mode: Only supports PDF, TXT, and MD formats. Filenames must match `^[\w\-. ]{1,128}\.(pdf|txt|md)$`.
  - Maximum file size: 100 MB.
  - PDF files must start with `%PDF-` (magic bytes validation).
  - Rate limit identifier: `sop_orchestrate`. Rate is determined by the `FLOW_CTL_PLAN` configuration.
  - Maximum concurrency of this endpoint per instance is determined by the `FLOW_CTL_PLAN` configuration in `server.conf`.

- Method

    POST

- URI

    `/api/v1/orchestrate/sop`

- Request Parameters

    **Mode A: File Upload (multipart/form-data)**

    | Parameter | Required | Type   | Range              | Default | Description                    |
    |-----------|----------|--------|--------------------|---------|--------------------------------|
    | file      | No       | file   | PDF/TXT/MD file    | -       | Solution package file to parse |
    | name      | No       | string | -                  | -       | Optional workflow name         |
    | binding | No | string | `instance` or `role` | `instance` | Generation mode |
    | catalog_version | No | string | Exact release | - | Only valid with `binding=role` |

    **Mode B: JSON Request Body (application/json)**

    | Parameter   | Required | Type   | Range | Default | Description                                    |
    |-------------|----------|--------|-------|---------|------------------------------------------------|
    | sop_content | Yes      | string | -     | -       | Natural language SOP steps (Markdown)           |
    | name        | No       | string | -     | -       | Optional workflow name                         |
    | binding | No | string | `instance` or `role` | `instance` | Generation mode |
    | catalog_version | No | string | Exact release | - | Only valid with `binding=role` |

    > **Priority**: If both a file and a JSON request body are provided, the file takes priority.

- Request Example

    **File Upload:**

    ```
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

    ------WebKitFormBoundary
    Content-Disposition: form-data; name="file"; filename="solution.pdf"
    Content-Type: application/pdf

    [PDF file binary data]
    ------WebKitFormBoundary
    Content-Disposition: form-data; name="name"

    My Workflow
    ------WebKitFormBoundary--
    ```

    **JSON Request Body:**

    ```http
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

    {
        "sop_content": "## Energy Saving Process\n1. Collect device status data\n2. Analyze energy consumption baseline\n3. Execute energy saving strategy",
        "name": "Energy Saving Assessment"
    }
    ```

- Response Parameters

    | Parameter | Type    | Description                                  |
    |-----------|---------|----------------------------------------------|
    | code      | integer | 201 indicates successful creation            |
    | message   | string  | Always `"PSOP generated and saved"`          |
    | status    | string  | `"success"`                                  |
    | data      | object  | The complete generated PSOP workflow object  |

    **PSOP Object Structure (data field)**: See [Appendix A: PSOP Data Structure](#appendix-a-psop-data-structure).

- Response Example

    ```json
    {
        "code": 201,
        "message": "PSOP generated and saved",
        "status": "success",
        "data": {
            "id": "a1b2c3d4-...",
            "name": "Energy Saving Assessment",
            "description": "Energy saving workflow generated based on SOP",
            "created_at": "2026-05-22T10:30:00.123456",
            "steps": [ ... ],
            "related_preflow": "preflow-uuid-...",
            "user_intent": "First 200 characters of the user's original SOP step text",
            "tags": []
        }
    }
    ```

- Error Codes

    | Status Code | Description                                                       |
    |-------------|-------------------------------------------------------------------|
    | 400         | Invalid filename, invalid PDF format, empty SOP content, chapter parsing failure |
    | 413         | File exceeds 100 MB                                               |
    | 422         | Missing `sop_content` field (Pydantic validation)                  |
    | 500         | Internal error during PDF parsing                                 |
    | 503         | Concurrency limit reached, server busy                            |

---

## 2. Intent Orchestration Interface

- Typical Scenario

    A user has only a high-level business intent description (e.g. "Help me perform a network-wide energy saving optimization") without needing to provide specific steps; the LLM autonomously plans and generates the workflow.

- Description

    Accepts natural language task intent, combines it with the available Agent list, and lets the LLM autonomously plan and generate a PSOP workflow, which is automatically saved.

- Interface Constraints

  - Rate limit identifier: `intent_orchestrate`. Rate is determined by the `FLOW_CTL_GENERATE_PSOP` configuration.
  - Maximum concurrency of this endpoint per instance is determined by the `FLOW_CTL_GENERATE_PSOP` configuration in `server.conf`.

- Method

    POST

- URI

    `/api/v1/orchestrate/intent`

- Request Parameters

    JSON Request Body (application/json):

    | Parameter | Required | Type   | Range | Default | Description                    |
    |-----------|----------|--------|-------|---------|--------------------------------|
    | intent    | Yes      | string | -     | -       | Natural language task intent   |
    | name      | No       | string | -     | -       | Optional workflow name         |
    | binding | No | string | `instance` or `role` | `instance` | Generation mode |
    | catalog_version | No | string | Exact release | - | Only valid with `binding=role` |

- Request Example

    ```http
    POST /api/v1/orchestrate/intent HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

    {
        "intent": "Help me perform a network-wide energy saving optimization",
        "name": "Network-Wide Energy Saving Optimization"
    }
    ```

- Response Parameters

    | Parameter | Type    | Description                                  |
    |-----------|---------|----------------------------------------------|
    | code      | integer | 201 indicates successful creation            |
    | message   | string  | Always `"PSOP generated and saved"`          |
    | status    | string  | `"success"`                                  |
    | data      | object  | The complete generated PSOP workflow object  |

- Response Example

    ```json
    {
        "code": 201,
        "message": "PSOP generated and saved",
        "status": "success",
        "data": {
            "id": "e5f6g7h8-...",
            "name": "Network-Wide Energy Saving Optimization",
            "description": null,
            "created_at": "2026-05-22T10:31:00.123456",
            "steps": [ ... ],
            "tags": ["Energy Saving", "Network-Wide"]
        }
    }
    ```

- Error Codes

    | Status Code | Description                                                  |
    |-------------|--------------------------------------------------------------|
    | 404         | No available Agents                                          |
    | 422         | `intent` field empty or missing (Pydantic validation, min_length=1) |
    | 503         | Concurrency limit reached, server busy                       |

---

### Role generation contract for sections 1 and 2

`binding=role` uses approved role/skill definitions and does not require any
registered instances. `catalog_version` selects an exact configured release;
omitting it selects the currently configured file for this new request only.
No directory or instance fallback is performed. Explicit model conflicts,
missing/duplicated actions and changed task identities fail validation.
Generation and save validation share a fixed request snapshot; directory
content changes before save cause a failed request rather than degraded success.

For example, an intent request may contain:

```json
{"intent":"Analyze the service","binding":"role","catalog_version":"approved-release-v1"}
```

For SOP files, send the same options as multipart form fields. For SOP JSON,
send them beside `sop_content`. Successful role PSOPs include `catalog_version`
and task-level `binding`, `agent` (role ID), `role_version`, `skill` (skill ID)
and `task_id`. Existing mixed role/instance templates can still be saved and
executed, while new role generation produces role tasks only.

Validation responses use HTTP 422 with a structured `message` in the normal
envelope, for example:

```json
{"code":422,"status":"error","message":{"code":"INVALID_ROLE_SKILL","message":"Model selected an unapproved role/version/skill reference"},"data":null}
```

Generation codes are `CATALOG_VERSION_UNAVAILABLE`, `NO_APPROVED_ROLE_SKILL`,
`INVALID_ROLE_SKILL` and `INVALID_GENERATED_WORKFLOW`. Invalid mode/version
parameter combinations also return 422. Model/service failures remain server
errors (500); they are not reported as generated-content validation failures.
See [Role Binding Pilot](Role%20Binding%20Pilot.md) for configuration and limits.

## 3. Search Workflow Interface

- Typical Scenario

    A user knows the task intent and wants to first check whether a matching existing PSOP workflow exists in the platform, then decide whether to execute it directly or generate a new one. Suitable for a "search first, then use" calling pattern.

- Description

    Accepts natural language intent, performs LLM semantic matching against saved PSOP workflows in the platform, and returns a list of the most relevant TopN result summaries (including workflow ID, name, description, tags, etc.) for the caller to select or proceed with further operations.

- Interface Constraints

  - Rate limit identifier: `retrieve_by_intent`. Rate is determined by the `FLOW_CTL_RETRIEVE_PSOP` configuration.

- Method

    POST

- URI

    `/api/v1/orchestrate/search`

- Request Parameters

    JSON Request Body (application/json):

    | Parameter | Required | Type    | Range      | Default | Description                                                     |
    |-----------|----------|---------|------------|---------|-----------------------------------------------------------------|
    | intent    | Yes      | string  | -          | -       | Natural language intent description for semantic matching       |
    | top_n     | No       | integer | 1 ~ 20     | 5       | Maximum number of results returned, sorted by relevance descending |

- Request Example

    ```http
    POST /api/v1/orchestrate/search HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

    {
        "intent": "Help me perform a network fault root cause analysis",
        "top_n": 3
    }
    ```

- Response Parameters

    | Parameter | Type   | Description                                              |
    |-----------|--------|----------------------------------------------------------|
    | code      | integer | 200 indicates success                                   |
    | message   | string | e.g. `"Found 3 matching workflow(s)"`                    |
    | status    | string | `"success"`                                             |
    | data      | array  | List of matching workflow summaries, sorted by relevance descending |

    **Structure of each data array element (WorkflowSearchResult):**

    | Parameter        | Type             | Description                                                  |
    |------------------|------------------|--------------------------------------------------------------|
    | workflow_id      | string (UUID)    | Unique workflow identifier, usable for subsequent execution  |
    | workflow_type    | string           | Workflow type, always `"psop"`                               |
    | name             | string           | Workflow name                                                |
    | description      | string \| null   | Brief workflow description                                   |
    | tags             | array[string]    | Tag list                                                     |
    | created_at       | string (ISO8601) | Creation timestamp                                           |
    | score            | float            | Relevance score (0~1), higher value = better match           |
    | user_intent      | string \| null   | Original user intent when this workflow was generated        |
    | related_preflow  | string \| null   | Associated PreFlow ID                                        |

- Response Example

    ```json
    {
        "code": 200,
        "message": "Found 3 matching workflow(s)",
        "status": "success",
        "data": [
            {
                "workflow_id": "a1b2c3d4-...",
                "workflow_type": "psop",
                "name": "Network Fault Root Cause Analysis",
                "description": "Automated network fault localization and root cause analysis workflow",
                "tags": ["Network", "Fault", "Diagnosis"],
                "created_at": "2026-05-20T09:15:00.000000",
                "user_intent": "Help me analyze network outage causes",
                "related_preflow": null
            },
            {
                "workflow_id": "e5f6g7h8-...",
                "workflow_type": "psop",
                "name": "SPN Fault Handling",
                "description": "SPN device fault detection and recovery process",
                "tags": ["SPN", "Fault", "Recovery"],
                "created_at": "2026-05-18T14:30:00.000000",
                "user_intent": "SPN fault localization and handling",
                "related_preflow": null
            }
        ]
    }
    ```

- Error Codes

    | Status Code | Description                |
    |-------------|----------------------------|
    | 500         | LLM search call failed     |

---

## 3.5 Get Workflow Details

- Typical Scenario

   After obtaining a workflow ID via the search interface, retrieve the full details of that workflow.

- Description

   Get the complete workflow definition by PSOP ID. Returns all steps, subtasks, jump conditions (next condition), and other details.

- Interface Constraints

  - Rate limit identifier: `get_workflow`. Rate is determined by the `FLOW_CTL_ONE_PSOP` configuration.

- Method

   GET

- URI

   `/api/v1/orchestrate/psop/{psop_id}`

- Request Parameters

   | Parameter | Type   | Required | Location | Description                |
   |-----------|--------|----------|----------|----------------------------|
   | psop_id   | string | Yes      | path     | PSOP workflow unique identifier |

- Request Example

   ```
   GET /api/v1/orchestrate/psop/06cb53d9-de27-4adf-9898-2eae5afcf888
   ```

- Response Parameters (data field)

   See [PSOP Data Structure](#appendix-a-psop-data-structure).

- Error Codes

   | Status Code | Description                     |
   |-------------|---------------------------------|
   | 404         | Workflow with the specified ID not found |
   | 500         | Internal server error           |

---

## 3.6 Get Workflow in BPMN Format

- Typical Scenario

   When an existing workflow in the orchestration center must be imported into standard BPMN tooling (Camunda Modeler, bpmn.io, ...) for viewing or further modeling, fetch its BPMN 2.0 representation by ID.

- Description

   Queries the workflow by PSOP ID. Internally the PSOP is first retrieved through the same query path as section 3.5, then converted server-side into BPMN 2.0 XML (`orchestrate.core.bpmn_converter`); BPMN has no storage of its own. Mapping rules: each PSOP step becomes a `bpmn:task` (subtask agent/skill recorded in `documentation`), `next` jumps become `sequenceFlow` elements, multi-branch jumps get an exclusive gateway, and jump conditions become `conditionExpression` elements. The document includes a `BPMNDiagram` DI section so viewers can render it directly.

- Interface Constraints

   - Rate limit identifier: `get_workflow`. Rate is determined by the `FLOW_CTL_ONE_PSOP` configuration.
   - The response is `application/xml` (a BPMN 2.0 document), not the JSON envelope of section 1.3.

- Method

   GET

- URI

   `/api/v1/orchestrate/psop/{psop_id}/bpmn`

- Request Parameters

   | Parameter | Type   | Required | Location | Description                |
   |-----------|--------|----------|----------|----------------------------|
   | psop_id   | string | Yes      | path     | PSOP workflow unique identifier |

- Request Example

   ```
   GET /api/v1/orchestrate/psop/06cb53d9-de27-4adf-9898-2eae5afcf888/bpmn
   ```

- Response Parameters

   The response body is the BPMN 2.0 XML document itself (`bpmn:definitions` root with `bpmn:process` and `bpmndi:BPMNDiagram`); `Content-Disposition` carries a suggested file name (ASCII fallback plus RFC 5987 `filename*=UTF-8''`, supporting Chinese workflow names).

- Error Codes

   | Status Code | Description                     |
   |-------------|---------------------------------|
   | 404         | Workflow with the specified ID not found |
   | 500         | Conversion or internal server error |

---

### SSE Event Contract

Execution endpoints return `text/event-stream`. Parse JSON from `data:` frames; ignore blank lines and heartbeat comments such as `: heartbeat`. The relay preserves SDK payloads rather than normalizing every frame to one schema. Most frames use `type`/`data`/`timestamp`; early errors can carry a top-level `message`. Fields are event-specific and optional unless defined by the producing SDK.

| Event family | Meaning and consumer guidance |
| --- | --- |
| `start` | Search/load/dispatch phase; may occur multiple times. Inspect `data.phase` when present. |
| `psop_update` | Workflow snapshot in `data.psop`; tolerate object or serialized JSON. |
| SDK events | Task, step, agent, routing, negotiation, notification and authorization events are passed through; the set is not a closed list of eleven events. Ignore/log unknown types safely. |
| `complete`, `error`, `cancelled` | Execution outcomes. Cancellation is not successful completion. Error text may be in data or top-level message. |

There is no center-generated `init` event and no guaranteed named `event: close` or JSON `close` frame. Detect transport EOF; EOF without a terminal outcome must not be interpreted as success. Heartbeats mean the connection is active, not that execution succeeded. This is a task execution stream, not the independent, task-state-agnostic Notification-T subscription.

The execution record retains a bounded tail of events (currently 1000) and prepends an `events_truncated` sentinel event with `data.dropped` when earlier frames were discarded (1000 retained events plus that marker). `execution_history` is not reconstructed by this relay and may be empty; do not promise complete replay from the stored record.

### Parsing Example (Python)

Set `OC_TOKEN` from the account login response, and `PSOP_ID` to an existing workflow ID. The example uses local HTTP; for HTTPS set `OC_BASE_URL` and trust a deployment CA via `REQUESTS_CA_BUNDLE`. If the listener requires mTLS, additionally supply your client certificate/key. Do not disable TLS verification in production.

```python
import json
import os
from urllib.parse import quote
import requests

base = os.environ.get("OC_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
psop_id = quote(os.environ["PSOP_ID"], safe="")
terminal = False
with requests.get(
    f"{base}/api/v1/orchestrate/execute/{psop_id}?lang=zh",
    headers={"Authorization": f"Bearer {os.environ['OC_TOKEN']}"},
    stream=True,
    timeout=(10, 60),  # read idle timeout; center heartbeats normally arrive every 15s
) as response:
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        kind = event.get("type")
        print(kind)  # Avoid printing sensitive payloads in shared logs.
        if kind in {"complete", "error", "cancelled"}:
            terminal = True
            break
if not terminal:
    raise RuntimeError("Execution stream ended without a terminal outcome")
```

## 4. Search and Execute by Intent Interface

- Typical Scenario

    The workflow library already contains usable workflows, and the caller supplies only a task description for automatic selection and execution. To review the selection first, search and then execute by ID.

- Description

    Searches existing PSOPs and dispatches the selected ID and snapshot to the Host Agent. This endpoint does not generate or save a new workflow. When the center finds no match, it still dispatches the raw intent; if the default Host's search also returns no result, it reports `No matching workflow found` through SSE `error` and records failure, not successful `complete`. For a new workflow, call `POST /api/v1/orchestrate/intent` to generate and save it first; on success read `data.id` and call `GET /api/v1/orchestrate/execute/{psop_id}`. Do not unconditionally retry the execution endpoint after a no-match error.

- Interface Constraints

  - Rate limit identifier: `ext_execute_auto`. Rate is determined by the `FLOW_CTL_START_PROCESS_STREAM` configuration.
  - Maximum concurrency of this endpoint per instance is determined by the `FLOW_CTL_START_PROCESS_STREAM` configuration in `server.conf`.
  - Response is an SSE streaming connection. Ensure the client supports long-lived connections of type `text/event-stream`.

- Method

    POST

- URI

    `/api/v1/orchestrate/execute`

- Request Parameters

    JSON Request Body (application/json):

    | Parameter | Required | Type   | Range | Default | Description                                                         |
    |-----------|----------|--------|-------|---------|---------------------------------------------------------------------|
    | task      | Yes      | string | 1–10000 characters | - | Task description to select an existing workflow; does not trigger generation |
    | name      | No       | string | At most 256 characters | - | Deprecated compatibility input; accepted but ignored. Name new workflows through the intent orchestration endpoint |

- Request Example

    ```http
    POST /api/v1/orchestrate/execute HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json
    Authorization: Bearer <account-token>

    {
        "task": "Help me perform a network fault root cause analysis"
    }
    ```

- Response Format (SSE Event Stream)

  See the SSE Event Contract above for payload/EOF/heartbeat semantics. A possible sequence is `start → SDK events → psop_update → complete → EOF`; ordering and repetition depend on the workflow. Failures and cancellations use `error`/`cancelled`, not a successful `complete`. Execution records are bounded, not a full transcript.

- Error Codes

    | Status Code | Description                              |
    |-------------|------------------------------------------|
    | 422         | Invalid request body or fields           |
    | 500         | Service failure before the stream starts |
    | 503         | Concurrency limit reached, server busy   |

    > Authentication, rate limits or dependencies can fail with their HTTP status before the stream starts. Once streaming starts, no-match/execution failures use SSE `error`; HTTP 200 is not execution success. The error payload is `{"type":"error","data":{"error":"No matching workflow found"}}` (other event fields omitted).

---

## 5. Execute Specific Workflow Interface

> **Workflow binding:** the center loads the requested PSOP and forwards its ID and a detached snapshot to the Host Agent without another intent search. `user_intent` supplies runtime context; it does not select a different workflow. Edits after snapshot capture apply only to subsequent executions. The Host rejects invalid or mismatched explicit metadata rather than falling back to an intent search. A missing requested PSOP returns HTTP 404 before dispatch; Host-side validation failures are reported through SSE `error` after streaming starts. The internal `/rest/v1/orchestrate/execute?psop_id=...` route follows the same binding rule. Intent-only execution remains a separate selection path.

- Typical Scenario

    The caller has found a target workflow ID via the [Search Workflow Interface](#3-search-workflow-interface), or already knows the PSOP ID from other channels, and wants to start execution directly. A typical flow is: search workflow → select target → execute specific workflow.

- Description

    Looks up the workflow by PSOP ID, starts execution via SSE stream, and pushes real-time execution progress and results.

- Interface Constraints

  - Rate limit identifier: `ext_execute_by_id`. Rate is determined by the `FLOW_CTL_START_PROCESS_STREAM` configuration.
  - Maximum concurrency of this endpoint per instance is determined by the `FLOW_CTL_START_PROCESS_STREAM` configuration in `server.conf`.
  - Response is an SSE streaming connection.

- Method

    GET

- URI

    `/api/v1/orchestrate/execute/{psop_id}`

- Request Parameters

    | Parameter    | Required | Type   | Location | Default | Description                                                       |
    |--------------|----------|--------|----------|---------|-------------------------------------------------------------------|
    | psop_id      | Yes      | string | path     | -       | PSOP workflow ID                                                  |
    | user_intent  | No       | string | query    | -       | Runtime user intent, injected as Agent context at execution time   |

- Request Example

    ```
    GET /api/v1/orchestrate/execute/a1b2c3d4-e5f6-7890-abcd-ef1234567890?user_intent=Check base station energy saving rate HTTP/1.1
    Host: your-host:5001
    ```

- Response Format (SSE Event Stream)

    Same SSE event format as the [Search and Execute by Intent Interface](#4-search-and-execute-by-intent-interface).

- Error Codes

    | Status Code | Description                             |
    |-------------|-----------------------------------------|
    | 404         | Specified PSOP does not exist           |
    | 503         | Concurrency limit reached, server busy   |

---

## 6. Query Execution Record List

- Typical Scenario

   Retrieve a summary list of historical execution records for monitoring or troubleshooting past executions.

- Description

   Returns execution record summaries in reverse chronological order. Each entry includes execution ID, associated PSOP information, status, and timestamps. Does not include full events and execution_history details.

- Interface Constraints

  - Rate limit identifier: `list_executions`. Rate is determined by the `FLOW_CTL_ALL_PSOPS` configuration.

- Method

   GET

- URI

   `/api/v1/executions`

- Request Parameters

   None.

- Request Example

   ```
   GET /api/v1/executions
   ```

- Response Parameters (data field)

   | Parameter     | Type      | Description                                      |
   |---------------|-----------|--------------------------------------------------|
   |               | array     | List of execution record summaries               |
   | execution_id  | string    | Execution record unique identifier               |
   | psop_id       | string    | Associated PSOP ID                               |
   | psop_name     | string    | Associated PSOP name                             |
   | started_at    | string    | Start time (ISO 8601)                            |
   | completed_at  | string    | Completion time (ISO 8601)                       |
   | status        | string    | Execution status: success, failed, stopped       |
   | step_count    | integer   | Number of steps executed                         |
   | error         | string    | Error information (if any)                       |

- Response Example

   ```json
   {
       "code": 200,
       "message": "Found 2 execution record(s)",
       "status": "success",
       "data": [
           {
               "execution_id": "7273ca6b-e75f-4a69-a645-b8bb59a3e622",
               "psop_id": "8598d5ee-56bc-4fd9-a039-865ec0137cc8",
               "psop_name": "Base Station Energy Saving Closed Loop",
               "started_at": "2026-06-02T07:01:03.994Z",
               "completed_at": "2026-06-02T07:01:25.492Z",
               "status": "success",
               "step_count": 4,
               "error": null
           }
       ]
   }
   ```

---

## 7. Query Execution Result Details

- Typical Scenario

    After workflow execution completes (or is interrupted), the caller needs to query the full record of a specific execution, including step-level execution history, Agent interaction events, final status, etc.

- Description

    Gets the execution record details by execution ID, including execution status, step history, Agent interaction events, completion time, error information (if any), etc.

- Interface Constraints

  - Rate limit identifier: `get_execution`. Rate is determined by the `FLOW_CTL_ONE_PSOP` configuration (internal mapping).

- Method

    GET

- URI

    `/api/v1/executions/{execution_id}`

- Request Parameters

    | Parameter     | Required | Type   | Location | Default | Description          |
    |---------------|----------|--------|----------|---------|----------------------|
    | execution_id  | Yes      | string | path     | -       | Execution record ID   |

- Request Example

    ```
    GET /api/v1/executions/exec-uuid-12345678 HTTP/1.1
    Host: your-host:5001
    ```

- Response Parameters

    | Parameter | Type    | Description                                      |
    |-----------|---------|--------------------------------------------------|
    | code      | integer | 200 indicates success                            |
    | message   | string  | Always `"success"`                               |
    | status    | string  | `"success"`                                      |
    | data      | object  | ExecutionRecord execution record object           |

    **ExecutionRecord Object Structure (data field)**: See [Appendix B: ExecutionRecord Data Structure](#appendix-b-executionrecord-data-structure).

- Response Example

    ```json
    {
        "code": 200,
        "message": "success",
        "status": "success",
        "data": {
            "execution_id": "exec-uuid-12345678",
            "psop_id": "a1b2c3d4-...",
            "psop_name": "Energy Saving Assessment",
            "started_at": "2026-05-22T10:30:00.000000",
            "completed_at": "2026-05-22T10:31:30.000000",
            "status": "success",
            "execution_history": [ ... ],
            "final_psop": { ... },
            "events": [ ... ],
            "error": null
        }
    }
    ```

- Error Codes

    | Status Code | Description                         |
    |-------------|-------------------------------------|
| 404         | Specified execution record not found |

---

## 8. Sandbox Verification Interfaces

These editor-oriented endpoints are available only under `/rest/v1/orchestrate` (internal, session/bearer auth). They are intentionally not exposed by the external API.

### Start a sandbox run

- Method / URI: `POST /orchestrate/sandbox/{workflow_id}/run`
- Request body fields:
  - `scenario`: `success`, `error`, `delay`, or `negotiation`
  - `runtime_intent`: optional text, max 10,000 characters
  - `templates`: optional array of Stub overrides, max 200 entries
  - `psop`: optional current-editor PSOP snapshot; when present it is validated and takes precedence over loading `workflow_id`
  - `lang`: `zh` or `en`; controls backend report text
- Response: `202` with `data.verification_id` and `data.status: queued`
- Error codes: `400` invalid snapshot/templates, `404` workflow not found, `429` rate limited, `500` server error

### Query, inspect, and delete reports

| Method | URI | Description |
|--------|-----|-------------|
| GET    | `/rest/v1/orchestrate/sandbox/verifications` | List persisted sandbox reports |
| GET    | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}` | Get report and events for a completed run |
| GET    | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}/events` | Get execution events |
| DELETE | `/rest/v1/orchestrate/sandbox/verifications/{verification_id}` | Cancel an active run or delete its persisted report |

A completed report payload contains `status`, `report`, and `events`. The `report` object includes verdict, static checks, execution path, context trace, Stub interactions, risks, suggestions, and optional error. Deletion cancels a queued/running task before removing its report and is permanent; the response returns `data.deleted = <verification_id>`.

### Stub template storage

| Method | URI | Description |
|--------|-----|-------------|
| GET | `/rest/v1/orchestrate/sandbox/templates/{workflow_id}` | List saved templates |
| PUT | `/rest/v1/orchestrate/sandbox/templates/{workflow_id}` | Replace saved templates; body is a JSON array |

Templates are limited to 200 entries. Extra fields and non-whitelisted response variables are rejected.

---

## Appendices

### Appendix A: PSOP Data Structure

| Field           | Type             | Description                                                              |
|-----------------|------------------|--------------------------------------------------------------------------|
| id              | string (UUID)    | Workflow unique identifier                                                |
| name            | string           | Workflow name                                                             |
| description     | string \| null   | Brief workflow description                                                |
| created_at      | string (ISO8601) | Creation timestamp                                                        |
| steps           | array[Step]      | List of workflow steps (see Step structure below)                         |
| related_preflow | string \| null   | Associated PreFlow ID (populated when generated by SOP orchestration)      |
| user_intent     | string \| null   | Original user intent when this workflow was generated                     |
| tags            | array[string]    | Tag list for classification and retrieval                                 |

**Step Structure:**

| Field        | Type                         | Description                                                                                          |
|--------------|------------------------------|------------------------------------------------------------------------------------------------------|
| name         | string                       | Step identifier (e.g. `"step1"`)                                                                      |
| type         | string                       | Step success condition: `"AllSuccess"` (all subtasks must succeed) or `"AnySuccess"` (any subtask succeeds) |
| subtasks     | array[Task]                  | Subtask list. Subtasks have no interdependencies and can execute in parallel                          |
| next         | array[JumpCondition] \| null | Jump condition list pointing to the next step. Empty value means unconditional sequential execution  |
| layer        | integer                      | Orchestration layer: 0 = execution layer (leaf Agent), 1+ = aggregation layer                        |
| context_from | array[string] \| null        | Context source step list. `["*"]` means include all direct predecessors (steps with edges flowing into this node). When null and layer > 0, automatically derived from graph topology |

**Task Structure:**

| Field       | Type   | Description                                                             |
|-------------|--------|-------------------------------------------------------------------------|
| task_id     | string | Unique task identifier (UUID)                                           |
| description | string | Task description                                                        |
| agent       | string | Agent name that executes this task                                       |
| skill       | string | Skill name required to execute this task                                 |
| status      | string | Task status: `"pending"` / `"running"` / `"success"` / `"failed"`       |

**JumpCondition Structure:**

| Field     | Type   | Description              |
|-----------|--------|--------------------------|
| step      | string | Target step name         |
| condition | string | Jump condition description |

---

### Appendix B: ExecutionRecord Data Structure

| Field             | Type             | Description                                                                                   |
|-------------------|------------------|-----------------------------------------------------------------------------------------------|
| execution_id      | string (UUID)    | Execution record unique identifier                                                            |
| psop_id           | string           | Executed PSOP workflow ID                                                                     |
| psop_name         | string           | Executed PSOP workflow name                                                                   |
| started_at        | string (ISO8601) | Execution start time                                                                          |
| completed_at      | string \| null   | Execution completion time (recorded even on failure)                                          |
| status            | string           | Execution status: `"running"` / `"success"` / `"failed"` / `"stopped"`                        |
| execution_history | array[object]    | Step-level execution history. Each entry contains `step` (step name), `task` (task description), `status` ("success" / "failed"), `output` (execution output) |
| final_psop        | object \| null   | Final PSOP snapshot with task statuses at completion time                                     |
| events            | array[object]    | Agent interaction event records (`agent_request` / `agent_response` events)                   |
| error             | string \| null   | Error information when execution fails                                                        |

---

### Typical Calling Flow

```
POST /api/v1/orchestrate/search  →  Caller reviews TopN results
                 │
         ┌───────┴──────────────────────┐
         │ Select existing workflow     │ No usable workflow
         │                              ▼
         │             POST /api/v1/orchestrate/intent
         │             Generate and save; read successful data.id
         └────────────────┬─────────────┘
                          ▼
GET /api/v1/orchestrate/execute/{psop_id}  →  SSE execution of selected workflow
                          │
                          ▼
GET /api/v1/executions  →  Obtain execution_id from the records list
                          │
                          ▼
GET /api/v1/executions/{execution_id}  →  Retrieve execution details
```

If automatic selection of an existing workflow is acceptable, call `POST /api/v1/orchestrate/execute` with only `task`. It is not a combined generation/execution endpoint; handle a no-match SSE error as described in section 4. Generation and execution have separate quotas, authentication and model requirements; successful generation does not guarantee successful execution.

## Internal frontend route inventory

These routes use `/rest/v1/orchestrate`, not `/api/v1`. Browser sessions and permitted internal identity policies apply; AgentCard writes require admin permission.

| Method | Relative path | Input/result |
| --- | --- | --- |
| GET | `/solution-packages` | List stored packages |
| GET / DELETE | `/solution-packages/{pdf_filename}` | Get/remove one stored package; missing filename returns 404 |
| PUT / DELETE | `/agent-cards/{organization}/{name}` | Admin-only registry proxy; PUT card name/organization must match URL |
| GET | `/dispatch` | Required `intent` and `agent_name`; optional `lang`; returns SSE for one registered Agent |
| GET | `/role-catalog` | Optional exact `catalog_version`; approved role/skill display projection from the configured release |
| POST | `/generate-from-intent` | `user_intent`, optional `workflow_name`, `binding` (default `instance`) and role-only `catalog_version` |
| POST | `/generate-from-preflow` | `preflow`, the same generation options, and `agent_cards` required only for instance mode |

Encode each path component (spaces included); never concatenate untrusted names into URLs. There is no DELETE-all `/solution-packages` route. Sandbox routes are documented in section 8.

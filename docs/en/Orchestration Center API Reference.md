# Orchestration Center API Reference

## Before You Begin

### Introduction

  Orchestration Center is a visual orchestration platform for multi-agent collaboration, providing the following RESTful API endpoints for external system integration:

  - **SOP Orchestration**: Upload PDF/TXT/MD files or submit natural language SOP steps to automatically generate a PSOP workflow.
  - **Intent Orchestration**: Submit natural language task intent and let the LLM autonomously plan and generate a PSOP workflow.
  - **Search Workflow**: Submit natural language intent to match existing workflows in the platform, returning the most relevant TopN workflows (including ID, name, description, etc.).
  - **Auto-Orchestration + Execution**: Submit a task description to automatically search for matching workflows and execute them; if no match is found, generate a new workflow and then execute it, with real-time progress and results pushed via SSE.
  - **Execute Specific Workflow**: Start execution based on a known PSOP ID, with real-time execution progress and results pushed via SSE.
  - **Query Execution Result**: Get detailed information about a workflow execution record by execution ID.

  All API endpoints use the base path **`/api/v1`**.

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
  | message   | string  | Error description                                  |
  | status    | string  | `"error"`                                          |
  | data      | object  | `null`                                             |

### Constraints and Limitations

  - All endpoints are protected by both concurrency control (Semaphore) and token bucket rate limiting (RateLimiter). See each endpoint's constraints for details.
  - The default service port is **5001**.

---

## 1. SOP Orchestration Interface

- Typical Scenario

     A user has a solution package document (PDF/TXT/MD format), or directly inputs natural language SOP step descriptions, and needs to automatically generate a multi-agent collaboration PSOP workflow.

- Description

     Accepts PDF/TXT/MD files (PDF parses the "5. Interaction Flow" chapter, TXT/MD reads the full content) or JSON-formatted SOP step text, and combines them with the available Agent list to generate a PSOP workflow via LLM, which is then automatically saved.

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

    **Mode B: JSON Request Body (application/json)**

    | Parameter   | Required | Type   | Range | Default | Description                                    |
    |-------------|----------|--------|-------|---------|------------------------------------------------|
    | sop_content | Yes      | string | -     | -       | Natural language SOP steps (Markdown)           |
    | name        | No       | string | -     | -       | Optional workflow name                         |

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

    ```json
    POST /api/v1/orchestrate/sop HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

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

- Request Example

    ```json
    POST /api/v1/orchestrate/intent HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

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

    ```json
    POST /api/v1/orchestrate/search HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

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

## SSE Event Type Description

The following execution endpoints (`POST /orchestrate/execute`, `GET /orchestrate/execute/{psop_id}`) push real-time execution progress via SSE (Server-Sent Events). Each SSE message has the format:

```
data: {"type": "<event type>", "data": {<event data>}, "timestamp": <timestamp>}
```

### Event Type Reference

| Event Type      | Description                | Trigger Timing         | Key data Field Contents          |
|-----------------|----------------------------|------------------------|----------------------------------|
| `init`          | Engine initialization complete | At execution start | `psop_id` — Workflow ID       |
| `start`         | Workflow execution begins  | After `init`           | `psop_id`, `message`           |
| `agent_request` | Task sent to Agent         | At each step start     | `agent` — target agent name, `request` — protobuf-formatted request body |
| `agent_response`| Agent returns result       | At each step completion | `agent` — source agent name, `response` — protobuf-formatted response body |
| `psop_update`   | Workflow status update     | After each step        | `psop` — complete PSOP JSON (with task status: pending/success/failed) |
| `complete`      | Workflow execution complete | After all steps are done | `psop_id`, `execution_history` — step-level execution history |
| `error`         | Execution exception        | On execution failure or cancellation | `psop_id`, `error` — error description |
| `close`         | SSE connection closed      | After `complete`/`error` | Empty `{}`                    |

### SSE Event Push Example

**Normal Flow Sequence:**
```
init → start → agent_request → agent_response → psop_update
  → agent_request → agent_response → psop_update
  → ... (repeat per step) ...
  → complete → close
```

**Error Interruption Sequence:**
```
init → start → ... → error → close
```

### Parsing Example (Python)

```python
import requests, json
resp = requests.get(
    "http://127.0.0.1:5001/api/v1/orchestrate/execute/{psop_id}?lang=zh",
    stream=True,
)
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    event = json.loads(line[6:])
    etype = event["type"]
    if etype == "agent_request":
        print(f"→ {event['data']['agent']}")
    elif etype == "agent_response":
        print(f"← {event['data']['agent']}")
    elif etype == "psop_update":
        psop = event["data"].get("psop", {})
        if isinstance(psop, str):
            psop = json.loads(psop)
        for step in psop.get("steps", []):
            print(f"  {step['name']}: {[t['status'] for t in step['subtasks']]}")
    elif etype in ("complete", "error"):
        print(f"[{etype}]")
        break
```

---

## 4. Auto-Orchestration + Execution Interface

- Typical Scenario

    A user directly submits a task requirement, and the system automatically determines whether a matching existing workflow exists: if yes, execute it directly; if no, generate one first and then execute. Suitable for "one-sentence-driven" end-to-end task scenarios.

- Description

    Accepts task description text, first performs LLM-based search for matching existing PSOP workflows. If a match is found, directly execute it via SSE stream; if no match is found, automatically invoke intent orchestration to generate a new PSOP, save it, and then execute it immediately. The entire process pushes real-time execution progress via SSE (Server-Sent Events).

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
    | task      | Yes      | string | -     | -       | Task description. System searches existing PSOP first; auto-generates if no match |
    | name      | No       | string | -     | -       | Optional workflow name (used in auto-generation scenario)            |

- Request Example

    ```json
    POST /api/v1/orchestrate/execute HTTP/1.1
    Host: your-host:5001
    Content-Type: application/json

    {
        "task": "Help me perform a network fault root cause analysis",
        "name": "Fault Root Cause Analysis"
    }
    ```

- Response Format (SSE Event Stream)

    Response is of type `text/event-stream`, with the following event format:

    ```
    data: {"type": "init", "data": {...}}
    data: {"type": "start", "data": {...}}
    data: {"type": "agent_request", "data": {...}}
    data: {"type": "agent_response", "data": {...}}
    data: {"type": "psop_update", "data": {...}}
    data: {"type": "complete", "data": {...}}
    event: close
    data: {}
    ```

    **SSE Event Type Description:**

    | Event Type     | Description                                                                                     |
    |----------------|-------------------------------------------------------------------------------------------------|
    | init           | Execution engine initialization, includes `psop_id`                                            |
    | start          | Execution start notification                                                                    |
    | agent_request  | Agent task dispatch event, includes `agent` (Agent name), `request` (dispatch request content) |
    | agent_response | Agent execution result return event, includes `agent` (Agent name), `response` (execution result content) |
    | psop_update    | PSOP workflow status update, includes `psop` (complete PSOP object with latest subtask statuses) |
    | complete       | All steps execution complete, includes `execution_history` summary                              |
    | error          | Execution failed, includes `error` description                                                  |
    | close          | SSE stream end signal                                                                           |

    Each event JSON contains three fields: `type` (event type), `data` (event data), `timestamp` (timestamp).

    After execution completes, the system automatically saves the `ExecutionRecord`. Details can be retrieved via the [Query Execution Result Interface](#7-query-execution-result-details).

- Response Example

    ```
    data: {"type":"init","data":{"psop_id":"a1b2c3d4-...","message":"Initializing execution engine"},"timestamp":12345.67}
    data: {"type":"start","data":{"psop_id":"a1b2c3d4-...","message":"Execution started"},"timestamp":12345.68}
    data: {"type":"agent_request","data":{"agent":"RAN Energy Saver","request":"{\"message\":...}"},"timestamp":12345.70}
    data: {"type":"agent_response","data":{"agent":"RAN Energy Saver","response":"{\"status\":{\"state\":\"TASK_STATE_COMPLETED\"},...}"},"timestamp":12346.50}
    data: {"type":"psop_update","data":{"psop":{"id":"...","steps":[...]}},"timestamp":12346.51}
    data: {"type":"complete","data":{"psop_id":"a1b2c3d4-...","execution_history":[...]},"timestamp":12347.00}
    event: close
    data: {}
    ```

- Error Codes

    | Status Code | Description                              |
    |-------------|------------------------------------------|
    | 500         | Auto-generation of PSOP failed           |
    | 503         | Concurrency limit reached, server busy   |

    > Runtime errors during execution are pushed via SSE `error` events and will not be reflected in the HTTP status code.

---

## 5. Execute Specific Workflow Interface

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

    Same SSE event format as the [Auto-Orchestration + Execution Interface](#4-auto-orchestration--execution-interface).

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
                        ┌─────────────────────────┐
                        │ POST /orchestrate/search │  ← Search workflows
                        │ { intent: "...", top_n } │
                        └──────────┬──────────────┘
                                   │ Returns TopN summary list
                                   ▼
                    ┌──────────────────────────────┐
                    │ Caller selects target ID      │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │ Match found        │                     │ No match
              ▼                    │                     ▼
   ┌──────────────────────┐       │          ┌─────────────────────┐
   │ GET /orchestrate/    │       │          │ POST /orchestrate/   │
   │   execute/{id}       │       │          │   intent             │
   │ SSE execute specific │       │          │ Intent orchestration  │
   │     workflow         │       │          │   → save → return    │
   └──────────┬───────────┘       │          └──────────┬──────────┘
              │                   │                     │
              └───────────────────┼─────────────────────┘
                                  │ Or directly via one-stop:
                                  ▼
                    ┌──────────────────────────────┐
                    │ POST /orchestrate/execute     │
                    │ Auto-search + execute /       │
                    │ generate + execute             │
                    │ (SSE real-time push)          │
                    └──────────┬───────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │ GET /executions/{id}          │
                    │ Query execution result details│
                    └──────────────────────────────┘
```

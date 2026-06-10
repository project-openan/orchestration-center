<!--
!/usr/bin/env python3
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

# Orchestration Center Development Guide

## 1. Feature Introduction
The Orchestration Center is a visual orchestration platform for multi-agent collaboration, supporting the definition of invocation relationships and execution flows between agents through a graphical workflow designer. The backend parses workflows and drives agent collaboration using a Python framework, helping users efficiently build, manage, and run complex Agent collaboration workflows.

This feature allows users to define custom implementations for different operations while providing default implementations for common operations. Through a unified abstract base class and handler registration mechanism, developers can flexibly extend system functionality without modifying core code.
In addition to the above custom implementations, this feature also provides an extensible Large Language Model (LLM) integration framework. The LLM module adopts a **configuration-driven** architecture — integrating a new model only requires editing `common/config/llm_config.json`, with no Python code needed.

## 2. Constraints and Limitations
- **Operational Constraints**:
  - Custom handler registration should be completed during application startup. Avoid registering during business processing.
  - The LLM module adopts a configuration-driven architecture. Integrating a new model only requires editing `common/config/llm_config.json`, with no Python code needed (a small amount of code is required only when adding a new authentication strategy).

## 3. Environment Requirements
- Python >= 3.10+

### 3.1 Setting Up the Environment

This module is designed to be part of a Python project. Ensure the following files are present in the project directory:

**Custom Handler Module:**
- `default_handle.py` - Contains base classes, registry, and default handlers
- `custom_handle.py` - Custom handler extension module (if needed)

**LLM Module:**
- `common/llm/__init__.py` - Module export file
- `common/llm/llm.py` - Unified factory functions
- `common/llm/config/config_reader.py` - JSON configuration reader
- `common/llm/config/llm_config.py` - ModelConfig dataclass
- `common/llm/provider/auth_strategies.py` - Header signing strategies
- `common/llm/provider/generic_llm.py` - Generic LLM Provider
- `common/config/llm_config.json` - LLM configuration file

### 3.2 Verifying the Environment

Verify default handlers:
```python
from common.custom.default_handle import HandlerRegistry, InterfaceType

# Verify that default handlers are available
handler = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
print(f"Handler loaded successfully: {type(handler).__name__}")
```
Verify LLM configuration:
```python
from common.llm import get_llm_instance

# Verify that LLM configuration loaded successfully
llm = get_llm_instance()  # Uses the "chat" capability by default
print(f"LLM loaded successfully: {llm.to_dict()}")
```

## 4. Usage Scenarios
### 4.1 Custom Handler Usage Guide
#### 4.1.1 Feature Introduction
**Core Capabilities:**
- **Abstract Base Class**: Defines a unified interface for all handlers
- **Default Implementations**: Provides built-in handlers for common operations
- **Custom Extensions**: Supports user-registered custom handlers

**System Architecture:**
The system adopts a registry pattern. The core components include:

| Component | Responsibility |
|-----------|----------------|
| BaseHandle | Defines the unified abstract interface for all handlers |
| HandlerRegistry | Manages handler registration and retrieval, providing default implementations as fallback |
| InterfaceType | Defines the enumeration of supported interface types |
| Default Handlers | Provide built-in implementations for common operations |
| Custom Handlers | User-extended implementations that override default behavior |

```
┌──────────────────────┐
│   Business Caller    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   HandlerRegistry    │◄──── Register custom handlers
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│     BaseHandle       │
│  (Abstract Base)     │
└──────────┬───────────┘
      ┌────┴────┬───────────────┐
      ▼         ▼               ▼
┌──────────┐ ┌──────────┐ ┌──────────────┐
│ Default  │ │ Default  │ │   Custom     │
│ Handler1 │ │ Handler2 │ │   Handler3   │
└──────────┘ └──────────┘ └──────────────┘
```
#### 4.1.2 When to Use Custom Handlers

The following scenarios require users to implement custom handlers:

| Scenario | Description | Example |
|----------|-------------|---------|
| Database Persistence | When `persistence_mode` is configured as `postgresql`, the default file storage handler cannot meet requirements; a custom handler is needed for database storage integration | Using PostgreSQL to store PSOP and execution records |
| Custom Storage Media | When using other storage media (e.g., MySQL, MongoDB, Redis), a custom handler is needed to implement the corresponding storage logic | Using MySQL as the PSOP storage backend |
| Storage Logic Customization | When additional business logic needs to be added to save/query/delete operations, a custom handler is needed to extend default behavior | Adding audit logging when saving PSOP |

**Configuration Notes:**

Configure the `persistence_mode` parameter in `etc/conf/server.conf`:

```properties
persistence_mode=file  # Uses default file storage; no custom handler needed
persistence_mode=postgresql  # Uses database storage; custom handler required
```

When `persistence_mode` is set to a value other than `file`, the system will prioritize user-registered custom handlers.

#### 4.1.3 Development Steps
Step 1: Import required modules
```python
from common.custom.default_handle import BaseHandler, HandlerRegistry, InterfaceType
```

Step 2: Create a custom handler

Create a custom class inheriting from BaseHandle and implement the handle method:
```python
class MyCustomHandle(BaseHandle):
    """Custom handler example"""
    
    def handle(self, *args, **kwargs):
        """
        Custom processing logic
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Processing result
        """
        # Custom implementation
        # Recommendation: add specific business logic here
        # Note: ensure the method is asynchronous
        result = "Custom result"
        return result
```
Step 3: Register the custom handler

Register the custom handler at application startup:
```python
# Register custom handler
# Note: Registration should be completed before business processing begins
HandlerRegistry.register(InterfaceType.QUERY, MyCustomHandle)
```
Warning: A later-registered handler will overwrite a previous handler of the same type. Ensure the registration order matches expectations.

Step 4: Use the handler

Retrieve and use the handler in business code:
```python
# Get handler instance
# HandlerRegistry will automatically return the registered custom handler or default implementation
handle = HandlerRegistry.get_handler(InterfaceType.QUERY)

# Use the handler for business execution
result = handle.handle(...)
```
Step 5: Complete example

Below is a complete custom handler implementation example:
```python
from common.custom.default_handle import BaseHandler, HandlerRegistry, InterfaceType

class SaveCustomHandle(BaseHandle):
    """Custom query handler"""
    
    def handle(self, query_params=None):
        """
        Custom query logic
        
        Args:
            query_params: Query parameter dictionary
            
        Returns:
            List of query results
        """
        # Example: implement custom query logic
        if not query_params:
            return []
        
        # Custom query implementation
        results = []
        # ... business logic
        return results

# Register
HandlerRegistry.register(InterfaceType.SAVE_PSOP, SaveCustomHandle)

# Use
handler = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
data = handler.handle({"id": 1})
print(data)
```
#### 4.1.4 Default Handler Reference

If no custom handler is registered, the system will use the following default implementations:

| Handler | Corresponding Interface Type | Functional Description |
|---------|-----------------------------|------------------------|
| SavePsopHandler | SAVE | Save PSOP |
| GetAllPsopsHandler | QUERY_ALL | Query all PSOPs |
| GetPsopHandler | QUERY | Query the corresponding PSOP by its ID |
| DeletePsopHandler | DELETE | Delete PSOP |

#### 4.1.5 Testing and Verification
Verify default handlers:
```python
from common.custom.default_handle import HandlerRegistry, InterfaceType

# Verify default handler
handler = HandlerRegistry.get_handler(InterfaceType.QUERY)
assert handler is not None, "Handler retrieval failed"
print(f"Currently used handler: {type(handler).__name__}")
```
Verify custom handler registration:
```python
from common.custom.default_handle import HandlerRegistry, InterfaceType

class TestHandle(BaseHandle):
    def handle(self, *args, **kwargs):
        return "test_success"

# Before registration
handler_before = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
print(f"Before registration: {type(handler_before).__name__}")

# Register
HandlerRegistry.register(InterfaceType.SAVE_PSOP, TestHandle)

# After registration
handler_after = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
print(f"After registration: {type(handler_after).__name__}")

# Verify functionality
result = handler_after.handle()
assert result == "test_success", "Custom handler did not take effect"
print("Verification passed")
```

### 4.2 LLM Module Configuration Guide

#### 4.2.1 Feature Introduction

`common/llm` is a unified LLM invocation module supporting three model capabilities: **Chat** (text generation), **Embedding** (text vectorization), and **Reranker** (result re-ranking). The entire module adopts a **pure configuration-driven** architecture, allowing new model integration without writing any Python code.

**Core Design:**

| Component | Responsibility |
|-----------|----------------|
| `ModelConfig` | Dataclass that loads model configuration from `llm_config.json` |
| `GenericLLM` | The sole generic Provider class, carrying the full interface of ask_llm / embed / rerank |
| `AUTH_STRATEGIES` | Pluggable Header signing strategy registry, with built-in `"aoc_signed"` |
| `get_llm_instance()` / `get_embed_instance()` / `get_rerank_instance()` | Retrieve singleton instances by capability |

**Directory Structure:**
```
common/llm/
├── __init__.py
├── llm.py                        # Unified factory functions
├── config/
│   ├── config_reader.py          # JSON file reader
│   └── llm_config.py             # ModelConfig dataclass
└── provider/
    ├── auth_strategies.py        # Header signing strategies
    └── generic_llm.py            # Sole generic Provider
```

**Caller API:**
```python
from common.llm import get_llm_instance, get_embed_instance, get_rerank_instance

# Chat — default get_llm_instance() is equivalent to get_llm_instance("chat")
llm = get_llm_instance()
reasoning, answer = llm.ask_llm("What's the weather like today?")

# Embedding
emb = get_embed_instance()
vector = emb.embed("A piece of text")  # Returns List[float]

# Rerank
rerank = get_rerank_instance()
results = rerank.rerank("Query", ["Candidate 1", "Candidate 2"])  # Returns List[dict]
```

> **Note:** Instances are singleton-cached; multiple calls return the same object.

---

#### 4.2.2 Configuration File Format

The configuration file is located at `common/config/llm_config.json`. The top level is grouped by capability, with each capability block configuring one model:

```json
{
  "chat":   { ... },
  "embed":  { ... },
  "rerank": { ... }
}
```

##### Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | `string` | No | Model description, used for logging |
| `model` | `string` | No | Model name, injected into the request body via the `$MODEL` placeholder |
| `url` | `string` | **Yes** | Model API endpoint address |
| `api_key` | `string` | No | API key; automatically used as `Authorization: Bearer` header when `auth` is null |
| `enable_thinking` | `boolean` | No | Thinking mode toggle, injected via the `$ENABLE_THINKING` placeholder |
| `auth` | `object/string/null` | No | Authentication strategy, see below |
| `headers` | `object` | No | Additional static HTTP headers, merged into the final request headers |
| `body` | `object` | **Yes** | Request body template, supports placeholders |
| `response` | `object` | **Yes** | Response extraction path |

##### Authentication Strategy (`auth` Field)

| Strategy Name | Form | Description |
|---------------|------|-------------|
| `null` | `"auth": null` | No special authentication; when `api_key` is non-empty, Bearer header is automatically added |
| `"aoc_signed"` | Object form (see example) | AOC platform signed Headers (`x-sg-*` series) |

Required parameters for `aoc_signed` object form:

| Parameter | Description |
|-----------|-------------|
| `app_key` | AOC application key |
| `app_secret` | AOC application key Secret |
| `authorization` | Bearer token header |
| `api_code` | API code |

Optional parameters have default values: `scenario_code` ("B99999999999"), `scenario_version` ("V1"), `ability_code` ("A999999999"), `api_version` ("1.0"), `test_flag` ("1").

##### Request Body Placeholders

`body` is a JSON object template that supports the following placeholders:

| Placeholder | Expands To | Applicable Capability |
|-------------|------------|-----------------------|
| `$MODEL` | Value of the `model` field | chat, embed, rerank |
| `$PROMPT` | The prompt argument of `ask_llm()` / `embed()` | chat, embed |
| `$QUERY` | The query argument of `rerank()` | rerank |
| `$DOCUMENTS` | The documents argument of `rerank()` (JSON array) | rerank |
| `$ENABLE_THINKING` | Value of the `enable_thinking` field | chat, embed, rerank |

> Full value replacement rules: If the string value exactly equals a placeholder (e.g., `"$MODEL"`), it is replaced with the original type (bool → `true`/`false`, list → JSON array); if the placeholder is only a substring (e.g., `"prefix-$MODEL"`), it is replaced as a string.

##### Response Extraction Path (`response` Field)

Defines dot-separated paths for extracting data from the API response JSON:

| Capability | response Key | Description |
|------------|-------------|-------------|
| chat | `answer` | Answer text extraction path |
| chat | `reasoning` | Reasoning/thinking process extraction path (optional) |
| embed | `embedding` | Vector array extraction path |
| rerank | `results` | Re-rank results extraction path |

Path syntax: `.` separates field names, numbers are array indices. For example:
- `"choices.0.message.content"` → `data['choices'][0]['message']['content']`
- `"data.0.embedding"` → `data['data'][0]['embedding']`
- `"results"` → `data['results']`

---

#### 4.2.3 Configuration Examples

##### Example A: OpenAI-Compatible API

```json
{
  "chat": {
    "description": "DeepSeek Chat",
    "model": "deepseek-chat",
    "url": "https://api.deepseek.com/v1/chat/completions",
    "api_key": "sk-xxxxxxxx",
    "enable_thinking": true,
    "auth": null,
    "headers": {},
    "body": {
      "model": "$MODEL",
      "messages": [{"role": "user", "content": "$PROMPT"}]
    },
    "response": {
      "answer": "choices.0.message.content",
      "reasoning": "choices.0.message.reasoning_content"
    }
  }
}
```

##### Example B: Customer Custom Model (Static Custom Headers)

```json
{
  "chat": {
    "description": "Customer X internal model",
    "model": "cx-model-v3",
    "url": "http://customer-api.internal:8080/generate",
    "api_key": "",
    "enable_thinking": false,
    "auth": null,
    "headers": {
      "X-Product": "psop",
      "X-Org-Id": "org-456"
    },
    "body": {
      "model_name": "$MODEL",
      "prompt_text": "$PROMPT"
    },
    "response": {
      "answer": "output.text"
    }
  }
}
```

##### Example C: Minimal Chat Configuration

```json
{
  "chat": {
    "url": "https://api.openai.com/v1/chat/completions",
    "api_key": "sk-xxx",
    "body": {
      "model": "$MODEL",
      "messages": [{"role": "user", "content": "$PROMPT"}]
    },
    "response": {
      "answer": "choices.0.message.content"
    }
  }
}
```

---

#### 4.2.4 When to Write Code

The vast majority of scenarios **only require editing the JSON configuration** — no code needed. Extension is required only in the following cases:

| Scenario | Approach | Notes |
|----------|----------|-------|
| Adding a new authentication strategy | Register a function in `provider/auth_strategies.py` | Function signature: `(params: dict) -> dict[str, str]` |
| The model's response format is extremely unusual | Very rare; response paths already cover OpenAI and mainstream formats | Response paths support arbitrary nested dot-separated paths |

> Earlier versions required writing a Python class for each new model (inheriting `BaseLLM`, implementing `_build_request_body`/`_parse_response`). **This is now deprecated. Please do not use the old approach.**

---

#### 4.2.5 Migrating from Old Configuration

The old configuration used the `LLMType` enum to distinguish models, e.g., `"aoc_chat_llm"` / `"openai_style_llm"`. The new architecture names by capability:

| Old Key | New Key | Additional Changes |
|---------|---------|--------------------|
| `openai_style_llm` | `chat` | `api` → `url` |
| `aoc_chat_llm` | `chat` | `extra.xxx` → `auth.xxx`; `request_template` (JSON string) → `body` (JSON object) |
| `aoc_embedding_llm` | `embed` | Same as above |
| `aoc_reranker_llm` | `rerank` | Same as above |

Placeholder syntax changes: `{prompt}` → `$PROMPT`, `{enable_thinking}` → `$ENABLE_THINKING`, `{query}` → `$QUERY`, `{documents}` → `$DOCUMENTS`.

---

#### 4.2.6 Testing and Verification

Verify that the LLM configuration has loaded successfully:

```python
from common.llm import get_llm_instance, get_embed_instance, get_rerank_instance

# Verify Chat model
llm = get_llm_instance()
assert llm is not None, "LLM instance retrieval failed"
print(f"Current Chat model: {llm.to_dict()}")

# Verify Embedding model
emb = get_embed_instance()
print(f"Current Embedding model: {emb.to_dict()}")

# Verify Reranker model
rerank = get_rerank_instance()
print(f"Current Reranker model: {rerank.to_dict()}")
```

Invocation test (requires the actual endpoint to be reachable):

```python
# Chat
reasoning, answer = llm.ask_llm("Hello")
print(f"Answer: {answer[:100]}")

# Embedding (requires valid embed configuration)
try:
    vec = emb.embed("Test text")
    print(f"Vector dimension: {len(vec)}")
except ValueError:
    print("Embedding configuration is a placeholder value; actual invocation is not possible")

# Rerank (requires valid rerank configuration)
try:
    results = rerank.rerank("Test query", ["Candidate 1", "Candidate 2", "Candidate 3"])
    print(f"Number of rerank results: {len(results)}")
except ValueError:
    print("Reranker configuration is a placeholder value; actual invocation is not possible")
```

## 5. FAQ
### 5.1 Custom Handler Not Taking Effect
**Symptom**: A custom handler was registered, but the default handler is still used when invoked.

**Possible Causes**:
- 1. The registration was performed after the handler was retrieved
- 2. The registered interface type does not match the one actually used
- 3. The custom handler did not properly inherit from BaseHandle

**Solutions**:
- 1. Ensure registration is completed at application startup, before any business processing
- 2. Check that the InterfaceType used during registration and retrieval is consistent
- 3. Confirm that the custom handler properly inherits from BaseHandle and implements the handle method

### 5.2 New Model Configuration Not Taking Effect?

**Symptom**: Modified `llm_config.json` but the changes did not take effect.

**Possible Causes**:
- 1. JSON format error (missing commas, mismatched brackets, etc.)
- 2. Incorrect capability key name (should be `chat`, `embed`, `rerank`)
- 3. The configuration file was modified after the service started (configuration is loaded on first module import)
- 4. Placeholder variable names in the `body` field are misspelled (should be uppercase, e.g., `$PROMPT` not `$prompt`)

**Solutions**:
- 1. Use a JSON validation tool to check the configuration file syntax
- 2. Confirm that the top-level keys are `"chat"`, `"embed"`, `"rerank"`
- 3. Restart the service after modifying the configuration so it reloads
- 4. Check that the `response` path matches the actual API response format

### 5.3 Model Invocation Error "Unable to extract..."

**Symptom**: `ValueError: Unable to extract ...` when calling `embed()` or `rerank()`.

**Possible Causes**: The extraction path configured in `response` does not match the JSON structure of the actual API response.

**Solutions**:
- 1. First call the API once using `curl` or Postman to obtain the actual response JSON
- 2. Adjust the `response` path based on the actual JSON structure, e.g., `"data.0.embedding"` or `"data[0].embedding"` are both acceptable
- 3. Confirm that array indices and field names in the path are case-sensitive

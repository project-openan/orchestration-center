# LLM Configuration File (llm_config.json) Description

This configuration file (`llm_config.json`) is used to define connection parameters for large language models, embedding models, and reranker models in different scenarios. It supports two types of APIs:
- **OpenAI Style**: Standard OpenAI-compatible interfaces (e.g., DeepSeek, GPT).
- **AOC Platform**: Models accessed through a specific gateway, requiring additional authentication and routing parameters.

## File Structure Overview

```json
{
  "openai_style_llm": { ... },    // General chat model
  "aoc_chat_llm": { ... },        // Enterprise internal chat model
  "aoc_embedding_llm": { ... },   // Text embedding model
  "aoc_reranker_llm": { ... }     // Search result reranking model
}
```

## Common Field Descriptions

Each model configuration includes the following basic fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | No | Model description, for notes only. |
| `model` | string | **Yes** | Model name, e.g., `deepseek-chat`, `Qwen3_32B`, `bge-m3`. |
| `enable_thinking` | bool | No | Whether to enable the model's "chain-of-thought" capability. Usually set to `true` for chat models and `false` for Embedding/ReRanker models. |
| `api` | string | **Yes** | Endpoint URL for API requests. |
| `api_key` | string | Conditional | API access key. Typically required for OpenAI-style interfaces; for AOC interfaces, authentication may rely on other fields in `extra`, so this can be `"dummy"` or left empty. |
| `extra` | object | No | Extended parameters, mainly for special authentication and request templates on the AOC platform. |

---

## Detailed Model Configuration

### 1. OpenAI-Style Model (`openai_style_llm`)

**Use Case**: Standard OpenAI-compatible services (e.g., DeepSeek, Qwen).  
**Required Fields**: `api`, `api_key`, `model`.

```json
{
  "openai_style_llm": {
    "model": "deepseek-chat",
    "enable_thinking": true,
    "api": "https://api.deepseek.com",
    "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

- **`api`**: The REST API address provided by the service provider.
- **`api_key`**: Secret key for authentication.
- `enable_thinking`: Enable as needed.

### 2. AOC Chat Model (`aoc_chat_llm`)

**Use Case**: Chat models (e.g., Qwen, ChatGLM) invoked through the enterprise's internal AOC gateway.  
**Key Fields**: The `extra` object must be complete, containing authentication and routing information.

| extra field | Description |
|-------------|-------------|
| `app_key` | Application key assigned by the gateway. |
| `app_secret` | Application secret key used for signature generation (or in conjunction with the authorization header). |
| `authorization` | Bearer token or other authorization header, typically in the format `Bearer <token>`. |
| `api_code` | Interface code identifying the specific model capability being called. |
| `api_version` | API version number, usually `"1.0"`. |
| `scenario_code` / `scenario_version` | Business scenario identifier and version. |
| `ability_code` | Capability code, often similar to `api_code`. |
| `test_flag` | Test flag: `"1"` for test environment, `"0"` for production. |
| `request_template` | JSON template string for the request body, supporting variable substitution. |

#### Variables in `request_template`

- `{prompt}`: The original text input from the user.
- `{enable_thinking}`: Corresponds to the `enable_thinking` boolean value in the current configuration (automatically replaced with `true`/`false`).

> Example template:
> ```json
> "{\"model\": \"Qwen3_32B\", \"messages\": [{\"role\": \"user\", \"content\": \"{prompt}\"}], \"chat_template_kwargs\": {\"enable_thinking\": {enable_thinking}}}"
> ```
> Before sending, the program replaces `{prompt}` with the user's message and `{enable_thinking}` with the configured value.

### 3. AOC Embedding Model (`aoc_embedding_llm`)

Used for text vectorization. The `extra` structure is similar to the chat model, but the `request_template` is different:

```json
{"request_template": "{\"model\": \"bge-m3\", \"input\": \"{prompt}\"}"}
```

- `{prompt}`: The text content to be vectorized.

### 4. AOC ReRanker Model (`aoc_reranker_llm`)

Used for relevance reranking of candidate document lists. The `request_template` accepts two variables:

```json
{"request_template": "{\"model\": \"bge-reranker-v2-m3\", \"query\": \"{query}\", \"documents\": {documents}}"}
```

- `{query}`: The user's query text.
- `{documents}`: The document list (**must be a JSON string representation of an array**, e.g., `["doc1", "doc2"]` embedded directly without additional quotes).

---

## Filling Guide (Security Recommendations)

1. **Placeholder Replacement**  
   Replace all strings in the form `<YOUR_XXX>` or `<...>` with your actual values:
   - Hostname, port, and endpoint ID in the API address.
   - All business parameters such as `app_key`, `app_secret`, `authorization`, `api_code`, `scenario_code`.

2. **Testing and Verification**  
   After filling in the details, you can use `curl` or Postman to simulate a request to ensure that authentication and request body format are correct.

## Frequently Asked Questions

**Q1: Does `openai_style_llm` need the `extra` field?**  
A: No, keep the original structure (this template does not provide that field).

**Q2: Some AOC models have `"dummy"` as the `api_key` — is it mandatory to keep it?**  
A: You can keep it or remove it; actual authentication is performed through `extra.authorization` and `app_key`/`app_secret`. If the gateway requires an `api_key`, replace it with a valid value.

**Q3: Must the model name in `request_template` match the top-level `model` field?**  
A: It is recommended to keep them consistent unless the gateway has special routing rules. They are already consistent in this template, and you can modify as needed.

---

## Usage Example (Python)

> Create a file named `llm_test.py` in the project root directory and run the test.
```python
from common.llm import get_llm_instance
from common.llm.config.llm_config import LLMType

if __name__ == '__main__':
    llm = get_llm_instance(LLMType.OPENAI_STYLE_LLM)
    reasoning, result = llm.ask_llm("who are you?")
    print(reasoning)
    print(result)
```
> Execute the script to test model connectivity.
```bash
./venv/bin/python3 test_llm.py
```
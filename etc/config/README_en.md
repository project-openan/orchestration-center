# Model configuration

Model definitions live in `etc/config/models.yaml`, a local file that Git
ignores — copy [`models.yaml.example`](models.yaml.example) to start. Secrets
never live there: a field names the environment variable that holds the value.
See [`.env.example`](../../.env.example) for local setup. Restart the process
after changing settings.

`LLM_CONFIG_FILE` selects a different model file (a relative path resolves
against the repository root). Docker Compose mounts one through
`LLM_CONFIG_HOST_FILE`.

Each key under `models:` is a capability (`chat`, `embed`, `rerank`, or a new
name backed by a registered protocol profile). `model` and `url` are required;
`provider` defaults to `openai_compatible` (OpenAI-compatible request/response contract; `openai` remains an alias)
and `aoc_signed` adds AOC request signing. Optional fields are `description`,
`timeout` (positive seconds), `verify_ssl`, and `enable_thinking`. Chat profiles
also support `stream`, `stream_total_timeout` (positive seconds, default 600),
`proxy` and `extra_body` for additional provider options. Protocol inputs such
as model/messages and the stream switch cannot be overridden by extra_body;
embedding/reranking profiles cannot enable chat SSE. Incomplete or truncated
streams fail rather than return partial answers. See [SPG/model streaming](../../docs/en/SPG%20Import.md).

```yaml
models:
  chat:
    provider: openai_compatible
    model: your-model
    url: https://provider.example/v1/chat/completions
    api_key_env: LLM_CHAT_API_KEY
  embed:
    provider: aoc_signed
    model: your-embedding-model
    url: https://gateway.example/embeddings
    auth:
      app_key_env: LLM_EMBED_AUTH_APP_KEY
      app_secret_env: LLM_EMBED_AUTH_APP_SECRET
```

`api_key_env` and every `*_env` entry name an environment variable; writing a
literal secret into the file is rejected. `api_key_env` is optional, so a
keyless local endpoint needs none. The AOC profile also accepts
`authorization_env` and the literal `api_code`, `api_version`, `scenario_code`,
`scenario_version`, `ability_code`, and `test_flag`.

`common/llm/config/model_sources.py` owns the versioned request/response
profiles. Adding a model that uses an existing protocol needs no Python change;
a different wire format requires registering and testing a new profile under the
name used in `provider`. Do not log request headers, bodies, or credentials.

For an installation whose model settings are still in `.env`, run
`python -m scripts.migrate_llm_config`. The tool writes `models.yaml`, validates
every profile and secret reference before changing either file, leaves secret
values in `.env`, and prints no secrets. The old JSON model file is no longer
tracked or read by the application.

If an older installation still has only `common/config/llm_config.json`, run
`python -m scripts.migrate_legacy_llm_json` instead. It moves credentials to
`.env` and non-secret definitions to `models.yaml`; unsupported custom
request templates require a provider profile before migration.

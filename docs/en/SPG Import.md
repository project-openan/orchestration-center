# SPG import and default workflow library

The 19 bundled solution packages and PSOPs are **planning examples**, not a
self-contained business execution environment. `samples/agentcard/spg_an_l4_agents.yaml`
is a planning capability catalog. Its loopback URLs are placeholders, not
servers started by the sample launcher. The launcher still implements only its
documented SPN demo agents. Planning cards do not claim Task-T support for
unimplemented external agents.

Before execution, deploy/register the actual business agents, verify their
business domain and skill contracts, replace endpoint URLs, configure protected
credentials and TLS, and run sandbox verification against the actual cards.
A missing Task-T extension must remain a failed readiness check. Do not falsify
card capabilities, disable validation, or interpret Stub success as real OMC
execution. A Stub-only example must use explicitly synthetic cards/endpoints.

## PDF and batch import

The internal upload endpoint and external single-chapter parsing recognize
`5. Interaction Flow` and numbering variants such as `6. Interaction Flow`.
The last PDF page is included. Missing required flow chapters and model
conversion errors fail explicitly; a failed upload does not create a package.
The upload API creates the PreFlow; generating/saving the PSOP is a separate step.

Configure chat in `etc/config/models.yaml` (or `LLM_CONFIG_FILE`), with secret
references resolved from the environment / `.env`. Select file, PostgreSQL or
MySQL through `persistence_mode`, and configure the appropriate `etc/conf/db/`
profile or environment aliases. Never put credentials in the command or PDF.

```powershell
python -m scripts.batch_spg_to_psop --pdf-dir D:/spgs --export-dir data/spg_import --dry-run
python -m scripts.batch_spg_to_psop --pdf-dir D:/spgs --export-dir data/spg_import
```

`generated` means exported but **not saved**. `success` means the configured
repository saved the PSOP and returned it on readback. Resuming checks the PDF,
chapter and capability-directory fingerprint, validates the exported PSOP/MD,
and checks the current target repository. Thus dry-run and failed-save exports
can be saved without another model call, while changing databases cannot be
mistaken for already having imported there. An edited existing document is not
overwritten. `--force` regenerates; legacy state without verified input
fingerprints is regenerated once. Keep the export directory private and do not
run concurrent batch writers against one checkpoint directory.

The generator rejects unmatched actions by default, even if a generic support
skill exists. An embedding application may explicitly provide `fallback_skill`
only when it owns and validates that fallback's business policy. A vaguely
related network/energy-saving skill is not a substitute for the requested domain.

## Defaults and upgrading installed examples

All three supported persistence modes import missing defaults idempotently.
Existing workflow IDs are never overwritten by startup seeding. The solution
package links are examples: their presence does not prove Agent readiness.

Seven prebuilt workflows shipped with wrong-domain skill bindings. New installs
receive corrected bindings, including distinct radio-service, IP-quality intent,
and core-network analytics planning capabilities. Existing installations must
not overwrite operator edits automatically. Preview the narrow migration:

```powershell
python -m scripts.migrate_default_psops
```

It reports `eligible`, `current`, `missing` or `conflict`. Stop editing/executing
the affected workflows, then use `--apply --backup-dir <private-backup-directory>`
to replace only exact known unedited predecessor documents. Each replacement is
backed up and read back; any changed document is a conflict and is left intact.
Review conflicts manually against the corrected seed, preserving local business
requirements. Do not run migration concurrently with edits: the legacy storage
port does not provide a compare-and-swap transaction. No migration is run merely
by starting the server or upgrading its code.

## Streaming model configuration

Chat may set `stream: true`, `stream_total_timeout: 600`, `proxy: http://...`
and `extra_body: {max_tokens: 8192}`. `timeout` remains the HTTP timeout;
`stream_total_timeout` is checked while consuming SSE events. Completion requires
an explicit normal `finish_reason: stop` or `[DONE]`; premature EOF, truncation,
in-band errors, non-SSE replies and empty answers fail. This is a finite model
generation stream, not a state-independent Notification-T subscription.

`extra_body` is for additional provider options, not overrides of `model`,
`messages`, `input`, `query`, `documents` or `stream`. Streaming is rejected for
profiles without a chat answer contract (including embedding and reranking).

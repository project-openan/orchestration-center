# Storage and multi-instance orchestration

The selected `persistence_mode=file|postgresql|mysql` now covers PreFlows, solution-package records/links, sandbox reports/templates and durable run documents/events, in addition to PSOPs and execution history. Built-in templates remain read-only resources. Original PDFs remain temporary parsing inputs.
SQL account sessions are shared opaque tokens: only their digests persist. Password changes and account deletion fence in-flight logins and invalidate existing sessions across replicas. File-mode authentication remains single-process.

## Migration and deployment

Back up and stop file-mode writers before migration. From the repository root:

```powershell
python -m scripts.migrate_operational_storage --source-root ./data --mode mysql --dry-run
python -m scripts.migrate_operational_storage --source-root ./data --mode mysql --initialize
```

Use `postgresql` for PostgreSQL. Connection settings and secrets use existing configuration sources. Run schema initialization once, before replicas start. Migration preserves sources, checks actual target documents on every retry, rejects conflicting content and never records dry-run as completed. The script migrates PreFlows, packages and sandbox documents; it does not re-import legacy PSOP/execution/user tables. Use existing backup/import tooling for those tables. Old alternate data directories can be supplied separately after reviewing dry-run and conflicts.

```properties
persistence_mode=mysql
deployment_mode=cluster
execution_lease_seconds=30
execution_max_active=16
execution_deadline_seconds=3600
```

Aliases: `PERSISTENCE_MODE`, `ORCH_DEPLOYMENT_MODE`; `ORCH_DATA_DIR` selects the file data root. File mode permits one local writer. Cluster mode requires one shared authoritative SQL database and a pre-initialized schema. Replica startup verifies schema rather than concurrently migrating it.
All replicas need matching role/auth/model configuration. Each API replica also schedules durable execution work.

## Execution contract

Both `/rest/v1/orchestrate` and `/api/v1` expose `POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events?after_seq=N`, and `POST /runs/{id}/cancel`. Submission returns 202 and supports Idempotency-Key. SSE accepts Last-Event-ID and returns replayable event IDs. A consistent state snapshot includes as_of_seq. Expired/gapped history fails explicitly; transport can redeliver events.
Cluster-mode legacy execution routes require Idempotency-Key or request_key and delegate to the durable API. The shipped designer does not send that key yet, so these routes answer 428 in cluster mode until the frontend update lands; programmatic clients must supply a stable key per execution, request cancellation explicitly, and may resume an accepted run after a same-tab refresh. Closing a durable subscription does not cancel the task. Single-mode legacy SSE retains its previous lifecycle.
Run ownership also applies to execution-history aliases. Existing history stays in its legacy shared workspace.

Submission, initial history and idempotency commit together. Terminal state, final event, result and history commit together. Transaction-aware PSOP adapters are required for atomic package linking; unsupported legacy handler overrides are rejected. Reimporting a source package while generation is in flight causes a revision conflict rather than linking stale output.

## Recovery limits

Lease fencing protects local writes; it cannot undo a network call. The actual dispatch envelope and send intent persist before Host creation. An ambiguous dispatch enters reconciliation_required and is never automatically sent again. Observed Host task/context IDs are retained. Queued sandbox inputs can be claimed by another replica under the original ID; uncertain running sandbox work is not restarted blindly.
Host durable acceptance, idempotency, task recovery and resubscription require separate protocol/deployment verification. This implementation does not promise automatic recovery from every Host crash or exactly-once business side effects. Cancellation is a request, not proof of remote termination.
Each run kind has a shared concurrency budget and at most 128 queued jobs. Events retain the latest 2000 entries; results/history are separate. Configure global ingress rate limits in addition to per-process connection protection. Keep vector caches replica-local.
File transactions use a commit journal and a shared read/write gate; platform power-loss durability is not claimed equivalent to SQL. Do not switch back to old files after new SQL writes without exporting and reconciling those writes.

## Verification

Use `tests/test_document_storage.py`, `tests/test_shared_auth_sql.py`, `tests/test_durable_execution.py` and `tests/test_sandbox_api.py`. Existing real-vendor integration jobs include the new storage tests. Real databases are opt-in via `ORCH_MYSQL_TEST_*` / `ORCH_POSTGRESQL_TEST_*` and use disposable generated schemas. Production load-balancing, Cookie/TLS/forwarded-header policy, SSE buffering and timeouts still need deployment acceptance.

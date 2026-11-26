# Role binding technical pilot

Role templates contain stable role and skill IDs. The center resolves them to
instances before dispatch. The Host verifies the frozen result and passes an
instance workflow to the existing workflow-engine SDK. The SDK is unchanged.

This pilot proves routing and transport behavior. It does not certify network
optimization capability or provide production admission for autonomous agents.

## Viewing and saving role templates

The designer preserves catalog/version metadata, original task IDs, role/skill
IDs, binding groups, step dependencies and context references when opening and
saving role or mixed role/instance templates. Import conversion leaves the
source object unchanged; canvas-only properties are excluded from saved PSOPs.

Any workflow containing a role task has read-only graph structure and task
content, including its instance tasks. Users can select, inspect, move and zoom
nodes, and change the workflow name, description and tags in the save dialog.
Deletion, reconnecting edges, merging nodes, dropping agents, clearing the
canvas and replacing skills are blocked. Ordinary instance workflows retain
their existing editing behavior.

Execution state is projected onto the original role graph by original task ID.
Resolved instance/skill details are displayed separately; they do not replace
the saved role identity. Resolution evidence and structured rejection reasons
are shown in the execution timeline. Errors identify canvas steps only through
exact original task IDs; an unmapped SDK task ID remains a workflow-level error.

Role workflows cannot use the current instance-only sandbox. The button
explains this restriction, and direct sandbox requests return HTTP 422 with
`ROLE_SANDBOX_NOT_SUPPORTED` before registry access or execution scheduling.
Instance sandbox behavior is unchanged. Display names come from the approved
projection of the template's exact catalog release, while IDs and versions
remain visible and are used for serialization. If that release is unavailable,
the designer retains the original IDs and shows a notice. The save dialog also
offers **Download design JSON**, which works without catalog access or saving.

## Generating role workflows

Both intent and PreFlow/SOP generation support `binding: "role"` and an optional
`catalog_version`. Omitting `binding` in an API request preserves instance
generation. The frontend generation selector defaults to **Role binding**; users can
explicitly select **Instance binding**. The graph builder retains its existing
instance editing behavior. Existing workflows keep their original binding mode.

Role generation does not load AgentCards or query the instance registry. It
uses only approved roles and approved skills from `role_catalog_path`. New
requests without a version select that configured release once; requests with
a version require an exact match. Existing save/execution loaders retain their
exact-version requirement and never fall back to another release.

The shared context fixes the release content for the request. Before saving,
the server checks its version, content fingerprint and approvals again, then
uses the existing save handler and CatalogGate. A changed release rejects the
request even if its version and skill IDs remain unchanged. This check does
not provide a transaction spanning other processes publishing catalog files;
publish release files immutably.

PreFlow actions receive distinct action IDs, including repeated descriptions.
Matching uses the joint role/version/skill identity. The structure stage must
preserve every selected task and its identity exactly once. Explicit instance
bindings, unapproved skills, wrong versions, role SelfLoop, duplicate IDs and
changes to the selected task set are rejected. No fallback agent is used.

The authenticated internal read-only endpoint
`GET /rest/v1/orchestrate/role-catalog?catalog_version=<version>` returns the
same approved display projection used for generation. It is rate limited and
does not expose paths, source documents, instances or credentials. It does not
introduce another catalog store or a catalog management API.

For HTTP examples, response envelopes and error codes, see the
[API reference](Orchestration%20Center%20API%20Reference.md).

Generation logs include request ID, entry, binding, catalog version, stage,
elapsed time and result/error code. They exclude raw model output and business
intent. Deterministic model responses and real local Host/worker transport
tests verify the technical path, not model quality or business capability.

## Configuration

Configure the center with a reviewed, exact-version role catalog and an instance
registry release. See the commented keys in `etc/conf/server.conf.example`:

```properties
role_catalog_path=/protected/releases/catalog.json
role_registry_path=/protected/releases/instances.json
role_execution_scope=operator-a/city-a/ran-domain-a
role_authorized_instances=technical-a,technical-b
```

`role_execution_scope` is a default; an execution request can provide a concrete
`tenant/site/business_object` scope. Registry scope tuples must cover the whole
requested tuple. `role_authorized_instances` is a deployment authorization
ceiling: a request can narrow it but cannot extend it. It is not a per-user
resource ACL. Caller identity comes from authenticated middleware; a caller's
claimed `caller_id` is ignored.

Set the same secret `ORCH_ROLE_DISPATCH_KEY` in the center and Host process
environments, with at least 32 bytes of secret material. Inject it through your
deployment's secret mechanism. It is not read from `server.conf`. The Host also
accepts explicit injection through `HostAgentConfig.role_dispatch_key`, whose
value is excluded from the configuration's `repr`.

Without a usable key, the center returns `ROLE_EXECUTION_NOT_ENABLED` before
creating transport. This default is unchanged. Upgrade both center and Host
together before enabling the pilot. The bundled role catalog remains draft and
does not authorize execution; tests use separate synthetic approved fixtures.

Role candidates may declare multiple interfaces, a complete authentication
declaration and required extensions. The projection admits a candidate when
its registry endpoint matches one declared HTTP+JSON interface, every
declared interface URL is clean HTTP(S) without embedded credentials, and
every security requirement references a scheme the card itself declares;
requirements without matching schemes are excluded before selection. At
dispatch the Host pins the SDK to the selected endpoint and enforces the
extension and authentication policy described below. Existing instance tasks
retain their original SDK credential handling, including login and Bearer
injection. Keep actual credentials in protected credential references, never
in AgentCard descriptions, URLs, extension content, snapshots or source
control.

## Dispatch contract

| Metadata key | Payload |
|---|---|
| `__orch_psop_id__` | Selected template ID |
| `__orch_psop__` | Instance-bound execution copy JSON |
| `__orch_binding__` | Versions, scope path and per-task binding evidence JSON |
| `__orch_cards__` | Full `role-pilot-v2` execution envelope JSON |
| `__orch_proof__` | HMAC-SHA256 signature and decimal-string issuance time |

The signature covers all four execution fields and the original runtime intent.
The Host rejects missing, changed, expired (over 300 seconds) or future-dated
(over 30 seconds) proofs. Fingerprints cover content consistency separately.
The proof provides authentication and a freshness window; it is not an
exactly-once or cross-process replay prevention mechanism.

The shared typed contract is `host_agent.role_contract.RoleSnapshot`. The center
retains its authoring model but validates the same wire rules. Unknown envelope
fields, malformed authorization collections and wildcard execution scopes fail
validation. Every role task must have exactly one binding and every selected
instance exactly one card. The execution copy may only make the declared role
to instance substitutions; the graph and legacy tasks remain intact.
Workflow task IDs, step names and binding groups retain their PSOP length
constraints; the catalog's 1024-character identifier limit does not apply to
these fields. Binding groups must still contain a non-whitespace character.

After checking the current registry for missing, duplicate or changed selected
cards, the Host reconstructs selected cards from frozen data and supplies them to
its existing client factory. It never replaces a frozen selected card with a
refreshed card. Status updates use a detached copy of the center's execution
workflow. The SDK receives `Workflow.from_dict(...)`, which removes role-only
authoring fields. Legacy execution remains on its existing path.

For role executions the Host additionally derives a dispatch projection: each
selected card is handed to the engine client with only the HTTP+JSON interface
matching the registry endpoint, so the SDK's protocol-version-based interface
selection cannot drift to another declared endpoint. The frozen snapshot,
fingerprints and audit evidence keep every declared interface; the projection
exists only on the dispatch path. Role-bound tasks then pass an extension
four-check before dispatch: activated URIs must be declared by the card, must
stay inside the supported set (Task-T only), required URIs must be activated,
and an activated Task-T must carry its `metadata` payload. The same four-check
runs on every negotiation reply content before the next request is sent, so a
control point cannot widen the extension envelope mid-interaction; a rejected
reply keeps the original task identity and flows through the SDK's
cancellation cleanup. Authentication is checked the same way: an agent that
declares schemes and requirements needs a credentials entry with a usable
login configuration or an injected `AuthProvider`. Requirements are
alternatives — one fully configured requirement satisfies the card, mirroring
the SDK interceptor. One combination is explicitly unsupported: multiple
schemes of the same requirement mapping to one case-insensitive
authentication header name (directly or through configured `auth_header`
values) are rejected up front with `AUTH_METHOD_UNSUPPORTED`, because the
SDK resolves such a group only through runtime token values, so the
requirement it adopts cannot be predicted. Supporting that combination
would require case-insensitive handling at the actual header merge, which
lives inside the SDK. `AuthProvider` output is verified only for role tasks
that require authentication: every scheme of one requirement must contribute
a non-empty, correctly formatted header (Bearer tokens in the
`Authorization` convention, API keys in their declared header; header names
and the Bearer prefix compare case-insensitively), or one of the alternative
requirements must be satisfied, or the output must carry a host-configured
custom header convention. The provider's output is also merged with
case-insensitive semantics before it reaches the SDK's exact-key header
merge: case-insensitive duplicates with equal values collapse into one
entry, different values are rejected as `AUTH_HEADER_CONFLICT`, and
scheme-derived names are rewritten to the effective spelling the
credentials side writes. That spelling mirrors the requirement the SDK's
credentials interceptor adopts — the first one whose every scheme carries
a usable credentials configuration (a configured `auth_header` wins over
the declared API key name over the `Authorization` convention); schemes
in skipped, incomplete groups contribute nothing even when configured,
and without an adoptable requirement the declared spellings apply. Equal
values dedupe and conflicting values trip the SDK's own conflict rejection
where the provider's headers meet the credentials-backed ones. Legacy
instance tasks and auth-less role tasks keep
the provider's existing semantics. Dispatch failures and rejected pre-checks
surface as `ROLE_DISPATCH_FAILED` with an `error_details.reason`
discriminator and the original execution, task and instance identity. Mapped
legacy instance tasks inside mixed executions keep their existing dispatch
behavior.

## Business policy context

The injected `control_point_factory` receives a `ControlPointContext` with an
optional `role_execution` value. For role execution it contains the verified
center execution ID, caller ID, concrete scope and task bindings. For legacy
workflows it is `None`. Business policies should obtain runtime object scope
from this validated context, rather than infer it from free text or shared
global state.

```python
def create_policy(context):
    execution = context.role_execution
    if execution is not None:
        return MyPolicy(role_execution=execution)
    return MyLegacyPolicy()
```

The SDK creates its own execution and task IDs. Inside a policy callback, use
`role_execution.task_identity(request)` to obtain the original PSOP `task_id`,
`step_name`, `subtask_index`, `sdk_execution_id` and `sdk_task_id`. Use
`role_execution.binding_for(request)` to retrieve that task's role binding;
it returns `None` for a mapped legacy instance or SelfLoop task. Unknown or
foreign execution/task IDs raise `LookupError`. Do not compare SDK request IDs
directly with the center IDs or infer identity from agent/skill names.

The Host maps the SDK's public `task_request` events by exact step and subtask
position and waits for registration before invoking `on_task` or `on_self_task`.
This covers identical concurrent tasks without changing their inputs, requests,
SDK IDs or event payloads. Missing local event delivery times out after five
seconds; inconsistent coordinates fail closed before business dispatch. The
bridge is scoped to one execution and forwards route/negotiation callbacks.
Negotiation callbacks can resolve their original task via `request.task`.

The Host owns transport and lifecycle. The policy owns request content and
business decisions. SelfLoop continues to call the policy locally.

## Diagnostics and verification

Rejected contexts use `INSTANCE_SNAPSHOT_MISMATCH` with a stable `reason`, such as
`ENVELOPE_SCHEMA`, `ROLE_REFERENCE`, `CARD_SKILL`, `REGISTRY_CARD_DRIFT` or
`REGISTRY_NAME_COLLISION`. Task IDs, role IDs, instance ID and binding group are
included where the verified data identifies them. Success and rejection logs
use `[RoleDispatch]` / `[RoleHost]` and execution IDs without logging proofs,
keys or raw validation payloads. Errors return through SDK events and SSE and
are persisted as failed execution records.

Host acceptance logs and rejections after snapshot validation include the
verified caller ID and scope. Rejections before that point mark those values
as `unverified`; claimed identity fields are never used as trusted audit data.
Proof failures retain the same public `UNTRUSTED_SOURCE` response. Internal
logs additionally use `diagnostic_reason` to distinguish `MALFORMED_PROOF`,
`INVALID_SIGNATURE`, `EXPIRED_PROOF` and `FUTURE_PROOF`. Freshness diagnostics
are assigned only after signature verification. A wrong key and changed
content both produce `INVALID_SIGNATURE` and cannot be distinguished reliably.
The internal diagnostic is excluded from event payloads and exception text.

Task mapping logs include both center and SDK IDs. Mapping failures preserve
`INSTANCE_SNAPSHOT_MISMATCH` and `error_details.reason=SDK_TASK_MAPPING` in SDK
task results.

Dispatch-time failures use `ROLE_DISPATCH_FAILED` with an `error_details.reason`
discriminator: `EXTENSION_UNKNOWN_ACTIVATED`, `EXTENSION_UNSUPPORTED`,
`EXTENSION_NOT_ACTIVATED`, `EXTENSION_PAYLOAD_MISSING`,
`AUTH_CREDENTIALS_MISSING`, `AUTH_METHOD_UNSUPPORTED`,
`AUTH_PROVIDER_UNSATISFIED`, `AUTH_HEADER_CONFLICT` or
`DISPATCH_FAILED` (login, token exchange and
network failures are not subdivided by matching exception text). Details carry
the execution ID plus the original task and instance identity; when a callback
cannot be mapped, only the execution ID is reported. `error_type` records the
exception class name; exception messages and authentication responses never
enter errors or logs.

Run the focused verification from the repository root:

```powershell
python -m pytest tests/test_host_role_snapshot.py tests/test_host_role_task_mapping.py tests/test_role_review_regressions.py tests/test_dependency_boundaries.py -q
```

The tests start and stop real local Host and worker HTTP A2A services. They cover
cross-site routing with an unchanged template, same-scope replacement, skill
translation, mixed instance tasks, local SelfLoop, a real legacy login/Bearer
exchange, registry drift rejection through SSE with failure recording, and
authenticated request propagation through all three execution APIs. One closed
loop dispatches the three expanded candidate types through real transports: an
authenticated worker (real login exchange, Bearer header on every business
request), a required Task-T worker (activated URI, metadata payload,
`A2A-Extensions` header asserted at the worker) and a multi-interface worker
whose registry-pinned endpoint receives every request while its higher-protocol
sibling receives none. A center-chain closed loop drives the same candidates
through the real orchestration-center path — catalog and registry files, live
projection, dispatch SSE and execution records — with a legacy instance task
mixed into the same execution, and a second chain asserts that a role
candidate without credentials is rejected with `AUTH_CREDENTIALS_MISSING`,
the original task identity and zero business requests. Unit coverage adds
provider-output validation (non-empty values, Bearer format, case-insensitive
header names, per-requirement combinations, custom conventions), the
requirement-alternatives credentials pre-check, negotiation reply guards, and
passthrough semantics for legacy and auth-less dispatches. Provider header
merge closed loops assert that a credentials-versus-provider case conflict
aborts the dispatch with zero business requests, that matching values
deduplicate to a single wire header, and that a legitimate lowercase provider
header still authenticates the request; further loops derive the effective
header from a credentials `auth_header` configuration and from a configured
scheme whose alternative declaration differs only by header-name case, each
with a same-value single-header pass and a conflicting-value rejection, and
from an incomplete AND group in front of a configured alternative — the
skipped group's configuration must not impose its spelling on the scheme
the SDK actually adopts — and from a requirement whose members share one
case-insensitive header name, which is rejected structurally with zero
logins and zero requests. No LLM or
external registry is needed. Regression cases also cover PSOP string boundaries,
identical concurrent tasks in AllSuccess/AnySuccess steps, event/callback order,
execution isolation, cancellation and mapping failures before dispatch.
API transport verification and real A2A execution are tested separately; mocked
API success does not certify business capability.

Two standalone synthetic instances support manual inspection: run
`python -m samples.role_pilot.technical_server` from the repository root; it
listens on local ports 18991/18992 by default (`--port-a`/`--port-b` override),
runs separately from `samples.start_agents_server`, and touches no registry, no
LLM and no external network. technical-a (card `Technical RAN A`, skills
`explore-a`/`Explore A`, scope `technical-demo/city-a/ran-a`) and technical-b
(`city-b`/`ran-b`) route by scope and skill; POST to
`http://127.0.0.1:18991/message:send` with `Content-Type: application/json` and
`A2A-Version: 1.0`, parts text
`{"tenant":"technical-demo","site":"city-a","business_object":"ran-a","skill_id":"explore-a"}`,
and a completed task returns a JSON text artifact carrying instance_id,
agent_name, scope, skill_id and technical_only; a scope or skill mismatch
returns a failed task. The responses are routing evidence only, not real
energy-saving assessment.

Production admission, per-user object authorization, database-mode acceptance and
business capability certification are outside this technical pilot. New
authentication schemes beyond the credentials file and `AuthProvider` injection
(such as mTLS), and extensions beyond Task-T, are not part of the current
supported set.

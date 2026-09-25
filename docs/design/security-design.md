<!--
SPDX-License-Identifier: Apache-2.0

Contributed to the OpenAN project under the Apache License, Version 2.0.
-->

# Security Design Proposal — Registry Center and Orchestration Center

**Status:** draft for discussion. Nothing in this document is implemented; the plan at the
end is a proposal, not a description of current behavior.

**Revision anchors** (every file:line reference below was read at these commits):

| Repository | Commit | Date |
|---|---|---|
| `project-openan/orchestration-center` | `4b1afd6` | 2026-09-09 |
| `project-openan/registry-center` | `e779c8f` | 2026-09-02 |

**Related:** orchestration-center issue #55.

## 1. Why this document exists

Both centers ship primitives that are sound in isolation — TLS with mutual client-certificate
verification, an AgentCard signature validator, per-endpoint rate limiting, an audit log, and
a token-based user store in the orchestration center. What is missing is a single statement of
*who* is calling, *what* they are allowed to manage, and what the shipped defaults enforce.
Today the answer depends on the deployment, and the shipped defaults answer "nobody, and
everything".

This document proposes one design across the two centers, split the way the issue discussion
framed it: authentication (human principals, and the genuinely new part — agent identity) and
authorization (management domains), plus the migration off the current temporary bootstrap
credential.

## 2. Current state (verified against the code, not the docs)

### 2.1 Orchestration center

| Surface | Mechanism today | Where |
|---|---|---|
| Internal API `/rest/v1/orchestrate/*` | Session token over DB-backed users (SHA-256 + salt), roles `admin` / `user`; `login` / `check` / `register` are public paths; session store is in-memory, single process | `orchestrate/server/auth.py:43-47, 98-116, 127-214, 284-325` |
| Activation gate | `is_auth_enabled()`: postgres mode → "does any user exist"; **file mode → `access_password` non-empty**; `TESTING` env short-circuits to disabled | `orchestrate/server/auth.py:98-116` |
| Shipped configuration | `enable_https=false`, `access_password=` (empty), `persistence_mode=file`, `verify_client=true` (only consulted on the TLS branch) | `etc/conf/server.conf` |
| External API `/api/v1/*` | No application-layer authentication at all; documented as mTLS "when `enable_https=true` and `verify_client=true`" | `orchestrate/server/auth.py:18-28`, `orchestrate/server/external_api.py` (only `RateLimiter` dependencies, e.g. `:95`) |
| Server startup | `enable_https=false` takes the plain-HTTP `uvicorn.run(app, ...)` branch — no TLS layer exists to carry that mTLS | `orchestrate/start.py:164-165` |
| Bootstrap credential | `seed_admin_if_empty("OpenAN@2026")` in postgres mode, flagged `must_change_password` on first login | `orchestrate/start.py:160`, `database/utils/user_store.py:270-278` |
| CORS | Allow-all in the current middleware stack | `docs/DESIGN.md` §5.3 |

**Consequence.** With the configuration as shipped, a caller that can reach the port can list,
create and delete workflows, generate PSOPs, execute them, and read execution records without
presenting any credential — through the internal API because `is_auth_enabled()` is false, and
through `/api/v1/*` because there is no application-layer check and no TLS layer under it. The
external router is also the path into connected agents, so an unauthenticated caller reaches
whatever the workbench agent can reach.

### 2.2 Registry center

| Surface | Mechanism today | Where |
|---|---|---|
| User / role model | None in-repo. Authentication and authorization are documented as host-provided | `README.md:216-221` and the architecture diagram ("Auth System (Host-provided)") |
| Transport | TLS 1.2/1.3 with mutual client-certificate verification | `agent_registry/middleware.py`, `agent_registry/server.py:253-262` |
| AgentCard signature verification | JWS (ES256/RS256), key from the backend store or the signer-supplied `jku`; `jku` fetch is fail-closed behind an operator allowlist and requires HTTPS | `agent_registry/signature/agent_card_signature_validator.py:120-150`, `agent_registry/signature/jwk_fetcher.py:45-98`, `agent_registry/server.py:89` |
| AgentCard operation isolation (owner) | Implemented, **off by default** (`owner.isolation.enabled=false`, `owner.validation.mode=strict`). Owner is the CN of the client certificate, read from the `X-SSL-Client-DN` header; agents with no stored owner stay writable by anyone | `agent_registry/config.py:65-66`, `agent_registry/server.py:353-420, 522, 629, 684` |
| Rate limiting, body/URL limits, audit | Present | `agent_registry/server.py:253-300`, `docs/en/Registry Center Security Guide.md` |

**Consequence.** With the default configuration, anyone able to reach the REST port can
register, replace and deregister AgentCards. Signature verification protects the *integrity* of
a card, and the allowlist protects against attacker-chosen key sources, but neither establishes
the *authority* to publish under a given name and organization.

### 2.3 What the two centers share

1. No single principal model: the orchestration center has users and sessions, the registry
   center has a client-certificate CN, and nothing states whether they denote the same person.
2. No default-deny anywhere: every gate is opt-in, and the shipped configuration opts out.
3. Agent identity is checked for integrity, never bound to an accountable operator.
4. No revocation path for agent identity (only for cards, by deregistration).
5. Permissive defaults are correct for a local demo and dangerous the moment the service is
   reachable from anywhere else — and nothing in the shipped configuration distinguishes the
   two situations.

## 3. Threat model (abridged)

| # | Threat | Path today |
|---|---|---|
| T1 | Unauthenticated orchestration / compute and LLM budget abuse | Anyone reaching the port drives `/api/v1/orchestrate/execute` |
| T2 | Tampering with workflows, PSOPs and execution records; reading them | Internal API with auth disabled in file mode |
| T3 | Agent identity spoofing — publishing an AgentCard under another organization's name | Registry REST API with `owner.isolation.enabled=false` |
| T4 | Impersonation at dispatch — the orchestrator treats a card as *identity* rather than a description | Orchestrator fetches/uses cards without pinning verification evidence |
| T5 | Confused deputy across centers — "the registry says this agent is X" used as an authorization statement | No operator binding on the card; registry has no authority concept |
| T6 | Bootstrap credential abuse | Well-known seeded password, usable before the forced change is honored |

**Trust boundaries.** browser → orchestration center; external client → orchestration center;
orchestration center → workbench agent; orchestration center → registry center; registrant →
registry center. The design below assumes nothing about the network between them.

## 4. Design principles

- **P1 — Fail closed.** No shipped configuration may expose a management API without a
  credential. Insecure operation is an explicit, loud, scoped opt-in.
- **P2 — One model per principal class.** Humans are accounts with roles; agents are
  identities with signing keys and an accountable operator. They are never the same row in a
  table.
- **P3 — Reuse, don't reinvent.** Agent identity builds on the AgentCard signing the A2A specs
  already define (JWS over an RFC 8785 canonical payload), not a parallel scheme.
- **P4 — One authorization decision.** "Which management domain does this resource belong to,
  and is this principal bound to it" is asked in exactly one place per service.
- **P5 — No secrets in code.** First-boot provisioning replaces compiled-in defaults.
- **P6 — Audit carries the principal.** Every privileged action records principal, domain,
  resource and outcome.
- **P7 — Explicit dev mode.** Local development is a named mode with a loopback bind, not the
  default posture.

## 5. Authentication

### 5.1 Human principals

A principal contract shared by both centers:

```
Principal {
  subject      : str    # stable id (username or host-issued sub)
  roles        : [str]  # admin | operator | viewer
  domain_ids   : [str]  # management domains this principal is bound to (§6.1)
  source       : enum   # "local" (user store) | "mTLS-CN" | "host-issued"
  issued_at    : ts
  expires_at   : ts
}
```

- **Accounts.** Keep the existing `users` model (`username`, `password_hash`, `salt`, `role`,
  `must_change_password`). Add `status` (active / disabled) so revocation does not require a
  delete.
- **Roles.** Keep `admin` and `user` for compatibility; the proposed target is
  `admin` (all domains) / `operator` (bound domains) / `viewer` (read-only in bound domains).
- **Credentials.** Passwords stay salted-hashed; the current SHA-256 + salt scheme should move
  to a memory-hard KDF (scrypt/argon2) with re-hash on successful login, so existing users
  migrate without a reset. Session tokens keep the current cookie + `Authorization: Bearer`
  extraction (`orchestrate/server/auth.py:217-232`) and the TTL knob.
- **Sessions are single-process today** (`auth.py:127-136`, referenced as issue #14). That is
  acceptable for the single-worker launch path the project ships, but it makes revocation and
  "log out everywhere" per-process. The design keeps the interface and requires a shared
  backend (DB table or Redis) before any multi-worker/multi-replica deployment; the middleware
  should refuse to start with more than one worker while the in-memory store is in use.
- **Host-provided authentication** (what the registry documents today) remains valid: a
  deployment behind an authenticating proxy passes `source="mTLS-CN"` or `source="host-issued"`
  principals, and the service maps them to roles from its own configuration. The point is that
  the mapping is explicit and deny-by-default, not implicit.

### 5.2 Agent identity (the new part)

**Definition.** An agent identity is the triple (card `name`, `provider.organization`, signing
key). Its *operator* is the human principal or host system accountable for it. A card is a
description of an agent; the operator binding is what makes it an identity.

**Enrolment** (registry center):

1. The registrant presents a client certificate (owner, as today) and a signed AgentCard.
2. The registry verifies the JWS over the canonical payload before the card is stored
   (existing validator), with key resolution restricted to the operator's backend keys or an
   allowlisted `jku` host (existing, fail-closed).
3. The registry records the verified operator — the certificate CN — as the card's `owner`.
   This is the durable agent ↔ operator link.
4. Registration under a name/org that already has a *different* stored owner is rejected;
   that path is a transfer of ownership, not a re-registration.

**Presentation at call time** (orchestration center):

- The orchestrator resolves the card through the registry and verifies the signature itself,
  or accepts the registry's verification result with the card digest attached. Either way, the
  execution record pins `card_sha256`, `key_id` and verification outcome, so a later audit can
  say which artifact was used, not just which name.
- The dispatch records the actor tuple `(caller principal, operator, agent id, card digest)`.
  "Agent X operating under orchestrator Y" is then a fact in the record, distinct from a human
  session, for the same reason agent credentials must not be user credentials.
- A callee that needs to check the delegation can resolve the card and the registry's operator
  binding; nothing in the call needs a new protocol extension for this to be auditable.

**Rotation and revocation.**

- Rotation: publish a new card with a new key, signed by the new key and carrying the previous
  `key_id`; the registry keeps the key history so signatures made before rotation remain
  verifiable for their validity window.
- Revocation: deregistration removes an agent from discovery; the card blacklist already in the
  registry is the revocation list for identity (not just for "malicious content"). The
  orchestration center must re-check the card it cached against the registry before dispatch
  if the cache is older than a configured freshness window, so revocation takes effect without
  a restart.

### 5.3 First-boot provisioning (replaces the compiled-in credential)

Rule: **a compiled-in default credential must not exist.** On first boot with an empty user
store the service obtains the initial admin credential from, in priority order:

1. a secret source named in configuration (`admin_initial_password_file`), or
2. an environment variable (`OC_ADMIN_INITIAL_PASSWORD`), or
3. a randomly generated one-time password written to a configured path with mode `0600` — the
   log records the *path*, never the value.

If none of the three can be satisfied and the service is not bound to a loopback address, it
refuses to start (P1). `must_change_password` stays as defence in depth, but it is no longer
the only control. In file mode the same rule applies to `access_password`: an empty value must
mean "authentication unconfigured", and the startup check must treat that as a failure — not
silently disable authentication as it does today (`auth.py:98-116`).

## 6. Authorization

### 6.1 Management domains

A **management domain** is the unit of ownership and the unit of authorization:

```
Domain { id, name, owner_principal }
Resource { id, domain_id, kind }   # kind ∈ {workflow, psop, execution_record, agent_card}
Binding { principal, domain_id, role }   # role ∈ {admin, operator, viewer}
```

- Every workflow, PSOP, execution record and stored AgentCard carries a `domain_id`.
  The registry already stores a per-card `owner`; that becomes the domain binding rather than
  a second concept.
- **Default deny.** A principal may act on a resource only through a binding for its domain.
  `admin` is the only role that crosses domains, and that fact is itself audited.
- Existing behavior maps onto this cleanly: cards with no owner are the "public" set, readable
  by all authenticated principals and writable only by admins — which is exactly what
  `owner.isolation.enabled=true` plus a stricter rule for owner-less cards should mean.
- Scope of the decision at a route handler is a single predicate:
  `can(principal, action, resource) → binding(principal, resource.domain_id) grants action`,
  evaluated in one dependency/helper, not scattered per endpoint.

### 6.2 Enforcement points

| Layer | Responsibility | Explicitly not its job |
|---|---|---|
| TLS / mTLS | Transport confidentiality; *assurance* that a certificate identifies the peer | Authorization. A valid client certificate is an identity, never a permission |
| Router / middleware | Authenticate the request into a `Principal`; rate-limit by principal, not only by IP; reject unauthenticated requests to non-public routes | Deciding which domain a resource belongs to |
| Route handler | Domain check (§6.1) for the specific resource | Re-authenticating the token |
| Registry | Verify card signatures; enforce owner/domain on register, replace, deregister | Deciding whether a caller may *use* an agent |
| Orchestration dispatch | Resolve + verify the card, record the actor tuple | Trusting a caller-supplied card |

Two concrete changes implied by the table:

- **External router default-deny.** Every `/api/v1/*` route requires a principal (mTLS client
  certificate or bearer token), except health/readiness endpoints that are explicitly listed.
  The current "mTLS handles the external API at the TLS layer" model
  (`auth.py:284-294`) is only true when HTTPS is on — and the shipped configuration has it off.
- **`X-SSL-Client-DN` is proxy-supplied and must be treated as such.** The owner read in
  `server.py:353-374` is trustworthy only because the certificate-terminating proxy sets it.
  The design should say so in the security guide and enforce it: strip the header at the edge,
  and require `forwarded_allow_ips` to cover only the proxy.

### 6.3 Fail-closed configuration contract

A startup check (`security_preflight`) evaluates the deployment before the server binds:

| `enable_https` | Credential source configured | Bind address | Outcome |
|---|---|---|---|
| `true` | yes | any | start; mTLS may add a principal |
| `true` | no | non-loopback | start, but every non-public route requires a principal from the host — i.e. no anonymous path exists |
| `false` | yes | any | start; warn that transport is plaintext |
| `false` | no | loopback | start only with `security.dev_insecure_mode=true`; log a warning at startup and an audit entry |
| `false` | no | non-loopback | **refuse to start**, with a message naming the two ways to fix it |

`security.dev_insecure_mode` must be echoed by the health endpoint so an exposed dev instance is
visible to operators. In the registry center the equivalent default flips
`owner.isolation.enabled` to `true` (a breaking change for deployments that rely on anonymous
card writes — see the open questions).

## 7. Migration plan

Each phase is independently reviewable and shippable.

**Phase 0 — fail-closed preflight (≤40 lines + tests).**
`orchestrate/start.py` calls a `security_preflight()` before deciding the bind branch;
`docs/en/...` and `README` describe the two ways to run a local demo. Registry: default
`owner.isolation.enabled=true`, with owner-less cards readable by all and writable by admins.
Tests: preflight matrix (unit), server refuses to start in the unsafe cell, dev flag permits a
loopback bind.

**Phase 1 — external API authentication and default-deny.**
Add a principal dependency on `/api/v1/*`; accept mTLS CN and bearer tokens; keep a
configuration-controlled public list for health. Update the API reference and the security
guide accordingly. Tests: 401 without a principal, 200/403 with one, proxy header handling.

**Phase 2 — agent identity end to end.**
Registry: owner on every registered card, ownership transfer rejected across different owners.
Orchestration: verify the card at dispatch, pin `card_sha256` / `key_id` in the execution
record, honour revocation with a freshness window. Tests: card signed with an allowlisted key
accepted, non-allowlisted rejected, revoked card refused after the window.

**Phase 3 — management domains.**
Add `domain_id` to workflows, PSOPs and execution records (migration: existing rows go to a
default domain owned by the bootstrapped admin), a bindings table, and the single `can()`
predicate on the handlers. Tests: cross-domain access denied, admin override audited,
viewer cannot mutate.

**Phase 4 — provisioning and session hardening.**
First-boot provisioning (§5.3), removal of the compiled-in default, KDF upgrade with re-hash on
login, and the multi-worker guard on the in-memory session store.

## 8. Open questions for the maintainers

1. **Where should the principal come from?** Should the orchestration center keep its own user
   store, or is authentication expected to be host-provided as the registry documents? This
   decides whether §5.1 is a shared user table or a mapping from a host principal.
2. **One trust zone or two?** Are the centers deployed inside one mTLS mesh with the same
   operator, or as independent services with different operators? It changes whether the
   domain model needs cross-service domain ids.
3. **May `owner.isolation.enabled` default to `true`?** If a deployment relies on anonymous
   card writes, the flip needs a deprecation window; I would rather ask than assume.
4. **Role granularity.** Is `admin` / `operator` / `viewer` enough, or does the project need a
   finer binding (for example per-workflow)?
5. **Document placement.** One document per repository, or one joint document with the other
   linking to it? This draft is a single joint document; moving it is cheap.

## 9. Non-goals

- Replacing an existing host IAM in deployments that already integrate one.
- New A2A protocol extensions. The proposal reuses AgentCard signing as-is.
- Changing A2A-T dispatch semantics; the actor tuple is a record, not a protocol change.
- Network/WAF/deployment hardening guidance beyond the fail-closed startup contract.
- A secret-management system: provisioning needs an *initial* credential, not a vault.

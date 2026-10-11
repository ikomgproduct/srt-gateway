# Dynamic UDP Multicast Intake - Dev Lead Implementer Handoff

## Decision

The Architect follow-up is approved for implementation. There are no blocking
questions for Product Lead or Architect.

This repair must preserve the approved Linux host-network worker model, HA
lease behavior, structured/flat route compatibility, Redis synchronization,
and existing FFmpeg multicast behavior.

## Required Outcomes

1. Validate multicast configuration for create and update even when the service
   is disabled. Disabled templates may overlap, but their multicast group, port,
   interface identity, and resolved bindings must be valid.
2. Treat `target_node: all` as exactly `primary` plus `backup`, regardless of
   which `node_bindings` keys are present.
3. Validate a supplied structured endpoint `interface_id` by exact inventory
   identity, then validate every resolved runtime role binding independently.
4. Serialize enabled multicast conflict admission across API requests and API
   replicas. The conflict query and database commit must occur within the same
   guard.
5. Require an explicit Grafana administrator password in production Compose and
   align every committed production environment example.
6. Remove obsolete current-production port-publication guidance.

## Compatibility Clarifications

### Legacy Worker Roles

Production roles `primary` and `backup` must match an inventory entry that is
eligible for that role, has `purpose: video`, and supports the `input`
direction.

Legacy/lab targets such as `worker_1` and `standalone` do not have matching
production inventory roles. Preserve their compatibility by requiring a
resolved IP belonging to a video/input inventory entry without requiring the
legacy role name in `node_roles`. Add regression coverage for a flat legacy UDP
multicast service targeting `worker_1`.

Do not weaken production role checks to achieve this compatibility.

### Endpoint Identity Versus Role Overrides

When `source.primary_endpoint.interface_id` is supplied:

- resolve exactly one inventory entry with that ID;
- require video purpose and input direction;
- require an endpoint `bind_ip` equal to that entry's IP;
- reject unknown IDs, duplicate IDs, Management entries, and IP mismatches.

After identity validation, resolve and validate every runtime role binding using
the existing precedence rules. A role-specific `node_bindings` override may use
a different interface from the endpoint. Validate that override by resolved IP
against a video/input inventory entry eligible for that production role.

Do not require the endpoint's own interface entry to be eligible for the backup
role when the backup resolves through a valid distinct override. Payloads that
do not supply `interface_id` retain the legacy IP-based path.

## Implementation Order

### 1. Add Policy Regression Tests

Update `tests/test_multicast_policy.py` and `tests/test_multicast_api.py` first:

- `all` resolves to primary and backup with complete, partial, or empty binding
  maps;
- either missing/ineligible role binding rejects enable/start for `all`;
- valid role-specific primary and backup bindings pass;
- exact interface identity rejects unknown, duplicate, Management,
  direction-ineligible, and IP-mismatched entries;
- a role override may differ from the structured endpoint when both are valid;
- a legacy flat `worker_1` multicast payload remains valid through IP fallback;
- disabled create/update rejects invalid group, port, or interface;
- disabled valid templates may overlap, while enable/start rejects the overlap.

### 2. Correct Multicast Policy Helpers

Update `backend/multicast_policy.py`:

- make `eligible_roles()` deterministic for `all`;
- separate exact endpoint identity validation from resolved role binding
  validation;
- apply role membership only to production primary/backup roles;
- retain the current binding precedence and legacy IP fallback;
- keep helpers pure and independently testable.

Do not add interface IDs to `NodeBinding` or change the persisted schema in this
repair.

### 3. Add The Admission Guard

Prefer a focused `api/multicast_admission.py` module containing an async context
manager:

- always acquire one module-level `asyncio.Lock`;
- when the active database dialect is PostgreSQL, execute
  `SELECT pg_advisory_xact_lock(:key)` with one stable signed 64-bit
  application-owned constant;
- use only the local lock for SQLite tests;
- keep the PostgreSQL lock transaction-scoped;
- release the local lock in `finally`.

The helper must not commit. The calling mutation owns validation, persistence,
commit, rollback, and post-commit Redis work.

### 4. Repair API Mutation Boundaries

Update `api/main.py` so create, update, and start all use the same rules:

1. Normalize the candidate.
2. Validate basic multicast configuration for every multicast candidate,
   including disabled candidates.
3. Apply existing HLS and route validation.
4. If the operation establishes or changes an enabled multicast claim, enter
   the admission guard.
5. Re-query enabled services, reject conflicts, persist, and commit before
   leaving the guard.
6. Roll back the session on a failed guarded mutation where needed.
7. Synchronize Redis and publish worker commands only after a successful commit
   and after leaving the guard.

Stop and delete remove claims and may remain outside the guard. Startup
validation occurs before serving requests and does not require the admission
guard. Existing invalid disabled records remain readable, but update/start must
meet the current validation contract.

Add a concurrent SQLite API test using `asyncio.gather`: two enabled creates
with different service IDs/names but the same protected bind claim must produce
exactly one success and one HTTP `422`. Add update/start concurrency coverage
where practical. Verify that PostgreSQL advisory SQL is dialect-gated and uses
a transaction-scoped lock.

### 5. Tighten Production Configuration

Update `docker-compose.production.yml`:

```yaml
GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}
```

Add a placeholder `GRAFANA_ADMIN_PASSWORD` to all four committed production env
examples, including worker-only examples, because Compose interpolates the full
file before profile filtering. Add static tests proving that production Compose
fails without the variable and renders with every committed example.

Do not add API authentication, TLS proxying, VPN configuration, or firewall
mutation. The current release relies on the documented private-DMZ, VPN-only,
firewall-allow-listed deployment boundary.

### 6. Align Documentation And Context

Update `README.md`, `UI_USER_GUIDE.md`, `docs/architecture.md`,
`docs/product-brief.md`, `.agent-context.md`, `backlog/tasks.md`, and the
implementation summary as applicable.

Remove current-production claims that:

- `PRIMARY_VIDEO_IP` or `BACKUP_VIDEO_IP` control worker media reachability;
- workers still depend on a fixed Docker-published UDP/SRT port window;
- host networking is pending rather than implemented.

Historical bridge limitations may remain only when clearly labeled as the
former model. Point test status to the newest report instead of retaining stale
pass counts in multiple places.

## Verification

Run the focused new policy/API/static tests, then the full regression suite.
Also run:

```powershell
node --check frontend/app.js
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.control-plane.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.primary.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.backup.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml -f docker-compose.production.video-zones.yml config --quiet
git diff --check
```

Repeat the clean no-cache API image/import check. Record exact results and any
environment limitations in the implementation summary.

## Definition Of Done

- All required role, interface, disabled-template, and compatibility tests pass.
- Concurrent conflicting admission yields one success and one `422`.
- Every enabled multicast mutation path holds the same admission guard through
  commit.
- Redis synchronization occurs only after committed state.
- Production Compose requires Grafana credentials and all examples render.
- Documentation describes the implemented host-network production model.
- Full regression and packaging checks pass.
- Implementation summary and project context are current for QA handoff.

## Escalation Triggers

Return to Architect/Product Lead before implementing any proposal that:

- replaces the PostgreSQL advisory guard with an in-memory-only production
  lock;
- adds a database schema migration or reservation table;
- changes HA ownership/failover semantics;
- permits Management as a media interface;
- changes host networking, Redis exposure, or FFmpeg multicast behavior;
- expands this repair into application authentication or TLS termination.

No current clarification is open. After implementation and Dev Lead review,
handoff to software QA; physical Linux multicast, HA/rejoin, network-isolation,
failure-stability, and normal-browser checks remain part of final release QA.

# Dynamic UDP Multicast Intake - Reviewer Follow-Up Architect Handoff

## Goal

Correct the Reviewer findings without changing the approved Linux host-network worker architecture, existing HA lease semantics, or flat/structured route compatibility.

## Inputs

- Product resolution: `docs/dynamic-multicast-port-review-product-handoff.md`
- Original architecture: `docs/dynamic-multicast-port-architect-handoff.md`
- QA rerun: `docs/dynamic-multicast-port-qa-rerun-report.md`
- Backlog item 13

## Architecture Decisions

### 1. Separate Validity From Conflict Admission

Multicast validation has two distinct stages:

1. **Configuration validity**, applied to every multicast create/update payload whether enabled or disabled:
   - IPv4 multicast group
   - administrator-approved port range
   - endpoint interface identity when supplied
   - resolved per-role media binding eligibility
2. **Running-intended conflict admission**, applied only when `enabled=true` or during start:
   - reject overlap with another enabled service's protected `(bind_ip, source_port)` key

Disabled templates may overlap, but they may not store a newly submitted invalid multicast group, port, or interface. Existing disabled legacy records remain readable; an update or start must pass the current contract.

### 2. Role Resolution

`eligible_roles()` becomes deterministic:

- `target_node == "all"`: validate `primary` and `backup`, regardless of which keys currently exist in `node_bindings`.
- `ha_mode == "active_passive"`: validate the target and configured failover role.
- Otherwise: validate the explicit target role.

For each role, retain current binding precedence:

1. `node_bindings[role].input_bind_ip`
2. `source.primary_endpoint.bind_ip`
3. role-local compatibility binding
4. top-level legacy `local_bind_ip`

An enabled/start request fails with HTTP `422` when any required role has no eligible resolved media binding. This validates fallback behavior rather than silently ignoring the missing role.

### 3. Interface Identity And Role Binding

Endpoint identity and runtime binding are related but not identical and must be checked separately.

When `source.primary_endpoint.interface_id` is present:

- resolve exactly one inventory entry by ID;
- require `purpose == "video"` and `input` direction;
- require `source.primary_endpoint.bind_ip` and require it to equal that entry's IP;
- reject unknown, duplicate, Management, direction-ineligible, or mismatched entries.

Then, for every eligible worker role, validate the resolved runtime bind IP against at least one video/input inventory entry allowed for that role. This second check covers role-specific `node_bindings`, which currently carry IPs but no interface IDs.

Payloads without `interface_id` retain IP-based legacy validation. Do not add interface IDs to `NodeBinding` in this repair unless Dev Lead proves it is necessary; that would expand the compatibility surface.

### 4. Transaction-Safe Conflict Admission

The database conflict query and state-changing commit must execute inside one admission guard.

Use a focused API-side async context manager, preferably in `api/multicast_admission.py`:

- Always take a module-level `asyncio.Lock` to serialize requests inside one API process and provide deterministic SQLite test behavior.
- On PostgreSQL, after taking the local lock, execute `pg_advisory_xact_lock` with one stable application-owned 64-bit key.
- Keep the advisory lock transaction-scoped; validate conflicts and commit the create/update/start inside the same context.
- Let exceptions roll back through the existing session lifecycle.

Why this design:

- claims are derived from JSON, target roles, fallback bindings, and enabled state, so a simple unique column/index does not represent the contract;
- no schema migration or reservation cleanup is required;
- PostgreSQL protects across multiple API processes/replicas;
- SQLite remains supported for the current in-memory test suite through the local lock;
- global serialization is acceptable because route mutations are low-volume control-plane operations.

Lock only operations that can establish or change an enabled multicast claim. Disabled validity checks do not need the database admission lock. Stop/delete may remain unlocked because they remove claims; a concurrent admission may receive a conservative temporary conflict but cannot create a duplicate claim.

### 5. Production Security Boundary

- Keep current direct API/UI and Grafana bindings; the site DMZ is private and reachable only through VPN.
- Document VPN access and firewall allow-listing as mandatory production prerequisites.
- Change production Grafana configuration to `GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}`.
- Add `GRAFANA_ADMIN_PASSWORD` to every committed production env example, including worker-only examples, because Compose interpolates required variables before profile filtering. Examples use placeholders only; server-local files hold real values.
- Keep full application authentication, TLS proxy implementation, VPN provisioning, and firewall mutation out of scope.
- Redis/Postgres isolation remains unchanged and must still be validated from DMZ.

### 6. Documentation Contract

Remove or rewrite current-production statements that mention:

- `PRIMARY_VIDEO_IP` / `BACKUP_VIDEO_IP` as active production media reachability controls;
- fixed production worker publish windows;
- UDP/SRT listeners needing a Docker-published worker port;
- the host-network model as still pending implementation.

Historical bridge limitations may remain only when explicitly labeled as the former model. Point test-result summaries to the current QA report instead of retaining several stale pass counts.

## Endpoint Flow

### Create/Update

1. Parse and normalize the payload.
2. Validate multicast configuration for all required roles, even when disabled.
3. Apply existing HLS validation.
4. If the normalized payload is enabled multicast, enter the admission guard.
5. Re-query enabled services, reject overlaps, persist, and commit before releasing the guard.
6. Synchronize Redis and publish commands only after successful commit.

### Start

1. Enter the admission guard before loading and promoting the candidate.
2. Normalize with `enabled=true`.
3. Validate all required roles and conflicts.
4. Commit `enabled=true` before releasing the guard.
5. Synchronize Redis and publish the explicit start command.

The guard must cover the authoritative conflict query and database commit. A helper that locks only the query but releases before commit does not fix the race.

## Files Likely Affected

- `backend/multicast_policy.py`
- `api/main.py`
- new `api/multicast_admission.py` if the guard is kept separate
- `docker-compose.production.yml`
- `.env.production.*.example` only if validation requires alignment
- `tests/test_multicast_policy.py`
- `tests/test_multicast_api.py`
- `tests/test_production_network_zone_static.py`
- `README.md`
- `UI_USER_GUIDE.md`
- `docs/architecture.md`
- `docs/product-brief.md`
- `.agent-context.md`
- `backlog/tasks.md`
- implementation and QA summaries

Worker and FFmpeg files should not change unless a regression test exposes a mismatch with the corrected role-resolution contract.

## Required Automated Tests

1. `eligible_roles(target_node="all")` returns primary and backup when bindings are complete, partial, or empty.
2. Enabled/start `all` route rejects when either role resolves no eligible media bind.
3. Valid `all` route passes with role-specific primary/backup bindings.
4. Exact endpoint interface ID rejects Management even when its IP equals a video entry's IP.
5. Exact endpoint interface ID rejects an IP mismatch and unknown/duplicate IDs.
6. Legacy payload without interface ID remains valid through eligible IP fallback.
7. Disabled multicast create/update rejects invalid group, out-of-policy port, and invalid interface.
8. Disabled valid templates may overlap; enable/start still rejects the conflict.
9. Concurrent conflicting creates produce exactly one success and one HTTP `422` under SQLite tests.
10. Where practical, add concurrent update/start admission coverage.
11. PostgreSQL guard SQL is dialect-gated and uses a transaction-scoped advisory lock.
12. Production Compose fails rendering without `GRAFANA_ADMIN_PASSWORD` and renders with every committed env example.
13. Static documentation tests reject obsolete current-production port-publication wording.
14. Full existing regression remains green.

## Verification Gates

```powershell
docker compose -f docker-compose-microservices.yml run --rm --no-deps api sh -c "pip install -q -r requirements-test.txt && python -m pytest -q"
node --check frontend/app.js
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.control-plane.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.primary.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.backup.example -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml -f docker-compose.production.video-zones.yml config --quiet
git diff --check
```

Also repeat the clean no-cache runtime import/start check that previously caught the missing `greenlet` package.

## Compatibility And Risks

- Existing invalid disabled records are not deleted or rewritten automatically; they fail on update/start until corrected.
- Global admission serialization adds negligible latency at expected control-plane mutation rates.
- PostgreSQL advisory locks require every enabled multicast mutation path to use the same guard. Missing one endpoint reintroduces the race.
- IP-only legacy payloads cannot express duplicate-IP interface identity; exact identity enforcement applies when the structured interface ID is present.
- Requiring Grafana's password may break deployments that relied on the unsafe default; this is an intentional production startup failure with a clear env correction.
- No database migration is required.

## Out Of Scope

- Full API authentication/authorization.
- HTTPS proxy implementation.
- VPN or firewall provisioning.
- Automatic failback.
- SRT Rendezvous.
- Netplan editing.
- Changing host networking, Redis exposure, HA leases, FFmpeg multicast URL behavior, or the first-release conflict key.

## Dev Lead Output

Dev Lead should review the transaction boundary and compatibility behavior, then issue an ordered Implementer handoff. Any proposal to replace the advisory guard with an in-memory-only production lock, add a database schema migration, change HA semantics, or relax Management exclusion must return to Architect/Product Lead.

Open questions: none.

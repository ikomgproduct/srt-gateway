# Dynamic UDP Multicast Intake - Dev Lead Implementer Instructions

## Verdict

Approved for implementation with the constraints and sequence below.

## Goal

Implement arbitrary operator-selected UDP multicast source ports from `1024-65535` by moving production workers to Linux host networking, while preserving existing service compatibility, worker HA behavior, control-plane isolation, and rollback safety.

## Required Inputs

- `docs/dynamic-multicast-port-product-handoff.md`
- `docs/dynamic-multicast-port-architect-handoff.md`
- `docs/architecture.md`, section `Dynamic UDP Multicast Intake`
- Backlog item 13

Do not alter the selected host-network architecture, Redis exposure model, conflict policy, or HA semantics without returning to Architect.

## Scope Boundaries

In scope:

- UDP multicast source validation and runtime mapping.
- Production worker host networking.
- Production Redis authentication and worker-facing connectivity.
- Operator port-policy feedback.
- Stable worker bind/join errors and retry suppression.
- Automated tests, deployment docs, and migration/rollback instructions.

Out of scope:

- IPv6 multicast.
- Different services sharing one bind IP and port.
- Automatic failback.
- SRT Rendezvous.
- Netplan or firewall mutation from the UI.
- Changes to lab/legacy Compose networking or Redis authentication.
- General FFmpeg structured destination/runtime redesign beyond what this source path requires.

## Implementation Order

### 1. Add Pure Multicast Runtime Helpers

Create a focused helper module rather than placing network policy in route normalization or endpoint handlers.

Required behavior:

- Parse `UDP_MULTICAST_PORT_MIN/MAX`, defaulting to `1024/65535`; reject invalid environment configuration at application startup.
- Identify structured UDP multicast from `source.protocol == "udp"` and `source.type == "multicast"`.
- For flat UDP services, infer multicast when `source_ip` parses as an IPv4 multicast address. Update `_source_from_flat()` so legacy multicast is not normalized as unicast.
- Resolve per-role input binding in this order: role-specific `node_bindings[role].input_bind_ip`, structured `source.primary_endpoint.bind_ip`, legacy `local_bind_ip`.
- Return every relevant bind key for the service's eligible roles: `(bind_ip, source_port)`.
- Validate IPv4 multicast group, configured range, non-empty bind IP, and eligible input/video inventory membership.
- Keep helpers deterministic and independently testable.

Do not add a database column. Existing structured JSON and flat fields are sufficient.

### 2. Enforce API Policy And Conflicts

Apply validation after normalization so structured and flat inputs follow one path.

Validation timing:

- Create with `enabled=true`.
- Update when the submitted service is `enabled=true`.
- Start before setting `enabled=true` or writing desired state.
- API startup before syncing an existing enabled service into Redis; invalid legacy services should remain visible with an actionable error rather than preventing the entire API from starting.

Disabled templates may overlap. Conflict validation excludes the current service on update/start and considers only other enabled services.

First-release conflict rule:

- Reject different service IDs when any resolved `(bind_ip, source_port)` overlaps.
- Do not distinguish multicast group for conflict purposes.
- The same service running on multiple roles remains allowed.

Return HTTP `422` with actionable details containing bind IP, port, and conflicting service name or ID.

Add:

```json
GET /api/runtime-policy
{
  "udp_multicast": {
    "min_port": 1024,
    "max_port": 65535
  }
}
```

Do not expose secrets or host firewall state from this endpoint.

### 3. Carry Structured Source Into Worker Runtime

`backend.models.ServiceConfig` currently drops structured `source` data. Add the smallest runtime models needed for source protocol, type, and primary endpoint. Preserve Pydantic compatibility with flat configs.

Update FFmpeg input construction:

- Structured endpoint address/port takes precedence for UDP multicast; flat fields remain fallback.
- Use the role-aware binding precedence from the helper.
- Multicast URL includes `localaddr`, `reuse=1`, and the existing timeout.
- Unicast UDP, SRT, RTMP, RIST, HLS, destinations, and flat compatibility must retain existing behavior.
- Test URL options by parsing the query where practical; avoid brittle ordering assertions.

### 4. Add Worker Preflight And Stable Failure State

Before launching multicast FFmpeg:

- Repeat multicast address and port-policy validation.
- Confirm the resolved bind IP exists on the local host with `psutil.net_if_addrs()`.
- Do not pre-bind a socket; FFmpeg remains the socket owner.

Add state fields:

- `error_code`
- `retryable`
- `config_fingerprint`

Required codes:

- `invalid_multicast_address`
- `invalid_bind_interface`
- `port_out_of_policy`
- `port_in_use`
- `multicast_join_failed`

Retry behavior:

- Watchdog and reconciliation skip non-retryable errors while the normalized configuration fingerprint is unchanged.
- A changed configuration clears the hold.
- An explicit start command may force one retry without permanently enabling a restart loop.
- Classify known FFmpeg bind/join stderr patterns. Unknown process/input failures retain existing retry/failover behavior.
- Publish `error_code` and `retryable` with existing metrics state; keep `error_msg` human-readable.

Do not change Redis lease ownership or active/passive selection.

### 5. Change Production Networking And Redis

In `docker-compose.production.yml`:

- Set `network_mode: host` on `worker-primary` and `worker-backup`.
- Remove their `ports:` sections.
- Keep API and all control-plane services on bridge networking.
- Worker code reads `WORKER_REDIS_URL`, falling back to `REDIS_URL` only for compatibility.
- Redis production service requires `REDIS_PASSWORD` and publishes only `${REDIS_BIND_IP}:${REDIS_PORT}:6379`.
- Single-server default bind is `127.0.0.1`; multi-server control-plane example uses the Management IP.
- API and telemetry use authenticated bridge URL; workers use authenticated loopback or Management URL.
- Update the Redis health check to authenticate without printing the password in normal output.
- Postgres networking remains unchanged.

Migration safety:

- Keep `docker-compose.production.video-zones.yml` for one release as a no-op compatibility file containing comments and `services: {}`. Old commands that include it must still render.
- Mark `PRIMARY_PORT_RANGE`, `BACKUP_PORT_RANGE`, and DMZ port-range variables deprecated and remove them from new production examples; extra values in existing local env files remain harmless.
- Do not change `docker-compose-microservices*.yml` in this task.
- Do not overwrite any server-local environment file.

Redis authentication is an atomic production migration: Redis command, health check, API URL, telemetry URL, and worker URLs must change together. Document that existing deployments must add `REDIS_PASSWORD` and matching URLs before recreation.

### 6. Update UI Policy Feedback

- Fetch `/api/runtime-policy` during frontend initialization with safe defaults `1024/65535` if unavailable.
- When source protocol is UDP and type is Multicast, apply the returned minimum/maximum to `sourcePort` and provide a concise validation message.
- Restore the generic `1/65535` HTML bounds for other source protocols/types.
- Add `sourceUdpType` to policy-refresh change handling.
- Preserve structured serialization, edit hydration, interface selection, and legacy fields.
- Bump frontend asset version query strings.

### 7. Documentation And Migration

After behavior passes automated checks:

- Change README/UI guide wording from approved-but-pending to implemented.
- Document the new production command without the video-zone override.
- Document new Redis variables and URL examples without real credentials.
- Document Linux-only host-network prerequisite, NIC/IP preflight, firewall and IGMP prerequisites, upgrade order, verification, and rollback.
- Keep prior-release bounded-port deployment as the rollback path; do not maintain two active production architectures.
- Update `.agent-context.md`, backlog item 13, architecture implementation state, and lessons learned.

## Required Tests

Add or update automated coverage for:

- IPv4 multicast detection and rejection of unicast/invalid addresses in multicast mode.
- Legacy flat multicast inference from `source_ip`.
- Port boundaries `1024` and `65535`; rejection of `1023`.
- Binding precedence for primary and backup roles.
- Enabled create/update/start conflict checks and disabled-template allowance.
- Structured and flat API round-trip and Redis desired-config compatibility.
- Exact multicast FFmpeg options including `localaddr` and `reuse=1`.
- Existing UDP unicast, SRT, RTMP, RIST, HLS, destination, and HA regression behavior.
- Worker local-interface validation, stable error codes, fingerprint suppression, config-change retry, and explicit retry.
- `/api/runtime-policy` and frontend policy application/hydration.
- Production Compose rendering for all four env examples.
- Host-network workers have no `ports:` mappings.
- Redis is loopback-only for single-server and Management-only for multi-server examples.
- Video-zone override remains a valid no-op when included.
- Redis/Postgres are absent from DMZ bindings.

## Manual QA Gate

The Implementer must report that these require target Linux hardware and hand them to QA if they cannot be run locally:

1. Send real MPEG-TS multicast on ports `1024`, `5500`, and `65535`.
2. Receive through Main Video, Backup Video, and DMZ Video.
3. Run the same service on primary and backup on one host and confirm both FFmpeg processes receive packets.
4. Confirm active/passive starts only the lease owner.
5. Confirm a second service with the same bind IP/port is rejected.
6. Confirm worker restart and desired-state reconciliation rejoin the group.
7. Confirm an invalid interface or occupied port produces one stable error without a restart storm.
8. Confirm API/UI and Grafana remain reachable and Redis/Postgres are unreachable from DMZ.

## Verification Commands

At minimum, run:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
node --check frontend/app.js
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml config
docker compose --env-file .env.production.control-plane.example -f docker-compose.production.yml config
docker compose --env-file .env.production.primary.example -f docker-compose.production.yml config
docker compose --env-file .env.production.backup.example -f docker-compose.production.yml config
docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml -f docker-compose.production.video-zones.yml config
git diff --check
```

Add focused test commands to the implementation summary. If the API image does not contain test dependencies, rebuild/install using the repository's established test workflow rather than skipping silently.

## Definition Of Done

- All required automated tests pass.
- Production Compose renders for every supported topology.
- No unrelated code or Compose files are changed.
- Existing flat services and Route Editor V2 payloads remain compatible.
- Existing lease/failover behavior remains intact.
- Security and migration notes are complete.
- Real multicast hardware checks are either passed or explicitly handed to QA as blocked-by-environment.
- Implementation summary lists files changed, commands run, skipped checks, upgrade steps, and rollback steps.

## Implementer Handoff

Goal: implement backlog item 13 exactly as scoped above.

Context: production workers currently use Docker bridge publication limited to `9000-9010`; the selected architecture moves only workers to Linux host networking and introduces separate authenticated worker Redis connectivity.

Output: code, production Compose/env changes, tests, and updated operator documentation.

Verification: full regression, production Compose matrix, frontend syntax/static tests, and real multicast QA handoff.

Open questions: none. Escalate any required change to host networking, Redis exposure, conflict policy, or HA semantics before proceeding.

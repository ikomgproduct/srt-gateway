# Dynamic UDP Multicast Intake - Architect To Dev Lead Handoff

## Goal

Prepare a scoped implementation plan that lets operators run UDP multicast sources on configured ports from `1024-65535` without publishing the complete UDP range through Docker bridge/NAT.

## Inputs

- Product handoff: `docs/dynamic-multicast-port-product-handoff.md`
- Architecture: `docs/architecture.md`, section `Dynamic UDP Multicast Intake`
- Backlog: item 13 in `backlog/tasks.md`
- Existing production deployment: `docker-compose.production.yml` plus the optional `docker-compose.production.video-zones.yml`
- Existing runtime: `api/schemas.py`, `api/route_normalizer.py`, `backend/models.py`, `backend/ffmpeg_builder.py`, and `worker/worker.py`

## Architecture Decision

- Use Linux `network_mode: host` for `worker-primary` and `worker-backup` only.
- Keep API, Redis, Postgres, telemetry, Prometheus, and Grafana on bridge/control-plane networks.
- Remove worker `ports:` mappings under the new model. FFmpeg binds only the selected port on the selected host video IP.
- Retire `docker-compose.production.video-zones.yml` after host-network migration is validated.
- Defer macvlan/ipvlan. It would require extra addresses for each worker on every media network, switch support, and a wider interface-inventory migration.

## Runtime Contract

For a structured UDP multicast source:

```text
udp://<multicast-group>:<source-port>?localaddr=<resolved-input-bind-ip>&reuse=1&timeout=5000000
```

Binding precedence:

1. `node_bindings[role].input_bind_ip`
2. `source.primary_endpoint.bind_ip`
3. Legacy `local_bind_ip`

The structured source endpoint supplies multicast group and source port. Legacy `source_ip` and `source_port` remain accepted and should be normalized without a database migration.

## Port And Conflict Policy

- Add `UDP_MULTICAST_PORT_MIN`, default `1024`.
- Add `UDP_MULTICAST_PORT_MAX`, default `65535`.
- Validate that structured multicast addresses are IPv4 multicast addresses.
- Validate that the resolved input bind IP belongs to an eligible video interface and is not Management.
- Different service IDs may not share one resolved `(bind_ip, source_port)` in the first release, even if their multicast groups differ.
- The same service may run on both worker roles when its target/HA mode intentionally starts both; `reuse=1` supports this candidate behavior and must be proven on the target Linux host.
- Active/passive behavior is unchanged: only the lease owner starts FFmpeg.
- Do not silently translate sender-facing ports.

## Redis And Control Plane

Host-network workers cannot rely on Compose DNS name `redis`.

- Introduce `WORKER_REDIS_URL` for worker services; keep `REDIS_URL` for bridge-network control-plane services.
- Single-server: publish authenticated Redis only on loopback and set workers to the loopback URL.
- Multi-server: bind authenticated Redis only to the Management address and restrict it by host firewall to approved worker management IPs.
- Update Redis health checks and all clients for authentication.
- Do not expose Redis or Postgres to DMZ.
- Postgres requires no worker-facing change.

## Failure And Retry Model

Add stable worker error codes:

- `invalid_multicast_address`
- `invalid_bind_interface`
- `port_out_of_policy`
- `port_in_use`
- `multicast_join_failed`

Configuration and bind errors are non-retryable. The watchdog must not restart them indefinitely. Editing the service or issuing an explicit start clears the hold and retries. Transient input loss remains subject to existing recovery behavior.

## Required Implementation Slices

### Slice 1 - Contract And Pure Validation

- Extend backend runtime models to consume structured UDP source type and endpoint data.
- Add pure helpers for multicast address, port policy, interface eligibility, binding precedence, and configured conflict detection.
- Preserve flat compatibility.
- Add unit and API tests before changing deployment networking.

### Slice 2 - FFmpeg And Worker Runtime

- Build multicast URLs with `localaddr` and `reuse=1`.
- Repeat local bind-IP and port-policy checks in the worker.
- Add stable error codes and non-retryable state.
- Keep existing lease ownership and target-node behavior unchanged.

### Slice 3 - Production Networking And Redis

- Change production worker services to host networking and remove worker port mappings.
- Add authenticated `WORKER_REDIS_URL` behavior for single-server and multi-server env examples.
- Add deployment preflight checks for host interface addresses, Redis reachability, and firewall prerequisites.
- Mark the video-zone override incompatible with the new release and remove it from current deployment commands after validation.

### Slice 4 - UI And Operator Feedback

- Keep the existing source-port input.
- For UDP multicast, set policy-aware minimum/maximum values and show actionable API/worker errors.
- Obtain policy values from an API runtime-policy response rather than hard-coding administrator overrides in JavaScript.
- Do not add firewall or Netplan controls.

### Slice 5 - Documentation And Release Migration

- Update README, UI guide, env examples, architecture, and server upgrade steps after behavior is implemented.
- Explicitly remove `docker-compose.production.video-zones.yml` from the new production command.
- Rollback is checkout of the prior release plus its bounded-port Compose command and env backup.

## Files Likely Affected

- `docker-compose.production.yml`
- `docker-compose.production.video-zones.yml`
- `.env.production.single-server.example`
- `.env.production.control-plane.example`
- `.env.production.primary.example`
- `.env.production.backup.example`
- `api/schemas.py`
- `api/main.py`
- `api/route_normalizer.py`
- a pure API/network validation helper
- `backend/models.py`
- `backend/ffmpeg_builder.py`
- `worker/worker.py`
- `frontend/index.html`
- `frontend/app.js`
- relevant API, builder, worker, frontend, and production Compose tests
- `README.md`, `UI_USER_GUIDE.md`, `.agent-context.md`, backlog, and architecture docs

## Dev Lead Review Focus

- Confirm whether Redis authentication can be added in this slice without breaking existing initialized deployments.
- Ensure production Compose has one canonical host-network path rather than leaving two competing production contracts.
- Ensure worker host networking is Linux-only and clearly rejected on unsupported environments.
- Require defense-in-depth validation at API and worker boundaries.
- Keep the conflict policy conservative; different groups sharing one interface/port remain deferred.
- Prevent scope growth into automatic failback, Netplan, UI-managed firewall rules, or generalized FFmpeg restructuring.
- Verify no existing flat services or active/passive lease behavior are broken.

## Verification Plan

1. Unit tests for multicast address validation, port boundaries `1024` and `65535`, binding precedence, and conflicts.
2. Builder tests for exact UDP URLs with `localaddr`, `reuse=1`, and legacy fallback.
3. Worker tests for stable errors, non-retryable holds, explicit retry, and unchanged lease behavior.
4. Compose rendering for single-server, control-plane, primary-worker, and backup-worker profiles; workers must have host networking and no `ports:` mappings.
5. Redis tests for loopback single-server access, Management-only multi-server access, authentication, and DMZ non-exposure.
6. Real FFmpeg sender/receiver tests on ports `1024`, `5500`, and `65535` through Main Video, Backup Video, and DMZ Video.
7. Same-service primary/backup concurrent reception on one host, with packet reception confirmed on both workers.
8. Different-service duplicate bind IP/port rejection.
9. Worker restart and desired-state reconciliation rejoin multicast correctly.
10. Full regression plus browser validation of create/edit hydration and operator errors.

## Deployment Preconditions

- Target production is Linux Docker Engine.
- Selected media NICs and IPs already exist on the host.
- Switch multicast/IGMP configuration supports the tested groups.
- Host firewall permits the approved UDP range only on intended media interfaces and source networks.
- No production listener below port `1024` is required for this feature.

## Out Of Scope

- IPv6 multicast.
- Different services sharing one bind IP and port.
- Automatic failback.
- SRT Rendezvous.
- Netplan or firewall mutation from the UI.
- Redis/Postgres HA redesign beyond secure worker connectivity.

## Expected Dev Lead Output

Dev Lead should approve or amend the slices, identify any migration/security blockers, and produce a final implementer instruction with exact sequencing and mandatory test gates. Any change to host networking, Redis exposure, conflict policy, or HA semantics should return to Architect before implementation.

## Primary References

- Docker host network driver: `https://docs.docker.com/engine/network/drivers/host/`
- Docker Compose service networking and host-mode constraints: `https://docs.docker.com/compose/how-tos/networking/`
- Docker macvlan tradeoffs: `https://docs.docker.com/engine/network/drivers/macvlan/`
- FFmpeg UDP options including `localaddr` and `reuse`: `https://ffmpeg.org/ffmpeg-protocols.html#udp`

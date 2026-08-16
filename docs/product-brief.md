# SRT Gateway Product Brief

## Product Summary

SRT Gateway is an operator-facing stream routing product for managing FFmpeg-based media pipelines from a web UI and REST API. It is intended for broadcast and facility workflows where operators need to create, start, stop, monitor, and fail over stream routes across primary and backup worker instances.

## Users

- Broadcast operators managing live stream routes.
- Engineering/operations teams deploying SRT/UDP/RTMP/RIST/HLS workflows.
- Support engineers diagnosing worker, network, and FFmpeg failures.

## Deployment Context

Initial production target:

- One physical server running two worker instances.
- API/UI on management IP `10.75.51.40:8000`.
- Grafana on management IPs `10.75.15.3:4000` and `10.75.51.40:4000`.
- Primary video worker bound to `10.70.15.3`.
- Backup video worker bound to `10.71.15.3`.
- Redis/Postgres are internal Docker services for single-server deployment.
- Multi-server deployments require Redis/Postgres reachable over the management network.
- Multi-server preview and HLS output requires shared storage mounted on the control-plane and worker hosts.
- Access is through the DMZ.

The architecture should remain portable enough to support single-server and multi-server hardware layouts.

## Core Workflows

Operators must be able to:

- Create a stream service.
- Select source protocol and fill only protocol-relevant fields.
- Configure destination output or HLS-only local output.
- Select target worker role: primary, backup, or all.
- Select video bind interfaces for primary and backup workers.
- Start, stop, edit, move, and delete services.
- See current status, active input, destination, worker target, preview, HLS links, and errors.

## Protocol Scope

Sources:

- SRT
- UDP
- RTMP
- RIST
- HLS

Destinations:

- SRT
- UDP
- RTMP/RTMPS
- RIST
- Raw URL for supported prefixes

HLS output:

- HLS is a generated local output mode, not a normal `destination_url` protocol.
- Low-res HLS generates 360p and 480p with a short rolling buffer.
- Full HLS generates 720p and 1080p with configurable buffer up to 24 hours.
- A normal destination can be omitted only when HLS output is enabled.

## Redundancy Requirements

- Production services target explicit primary/backup worker roles.
- Active/passive ownership uses Redis leases.
- Manual failback is the safe default.
- Only the active worker should generate HLS unless intentionally changed later.
- The UI must distinguish target binding from active lease owner.

## Binding Requirements

- Users must be able to select binding interfaces.
- The target production contract is `node_bindings` with primary/backup input/output bindings.
- Legacy `local_bind_ip` remains compatibility/lab fallback.
- Binding UI uses dropdowns populated from installed/configured hardware inventory, not free text.
- Visible production binding is primary/backup only; single-worker compatibility remains backend/lab behavior.

## Operational Guardrails

- Full HLS remains capped at 24 hours of buffer.
- Full HLS service count is configurable and limited by default.
- HLS startup checks minimum free disk and optional storage quota settings.
- Generated HLS artifacts are cleaned on service stop.
- Operators should size CPU/GPU and storage for transcoding load before enabling many Full HLS services.

## Non-Goals For Current Slice

- Smart HLS passthrough/cache.
- Automatic failback.
- Full authentication/authorization model.
- Redis/Postgres HA design beyond deployment guidance.
- Removing backend compatibility for `worker_1`.

## Acceptance Themes

- Product UI should be operator-safe and not expose confusing lab-only defaults.
- Existing services must remain compatible.
- Production compose changes must be explicit and must not overwrite server-local compose files.
- `docker-compose.production.yml` is the production HA contract for both single-server and multi-server layouts.
- Older compose files are lab/legacy compatibility paths.
- Full HLS must remain guarded by service count and disk capacity controls before production use.

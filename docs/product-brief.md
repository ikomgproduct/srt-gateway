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

Updated site network model for the next architecture cycle:

- Main Video: `eno1`, `10.70.15.3`, internal video input/output.
- Backup Video: `eno2`, `10.71.15.3`, internal video input/output.
- DMZ Video: `eno3`, `10.75.51.40`, public/external video input/output.
- Management: `eno4`, `10.75.15.3`, API, SSH, Grafana/admin, and internal control-plane communication.

Product decisions for this model:

- DMZ Video must be selectable for both input and output on both primary and backup workers.
- Main Video and Backup Video are paired internal redundant paths.
- If Main Video is selected as the primary internal path, the paired redundant path should use Backup Video.
- If Backup Video is selected as the primary internal path, the paired redundant path should use Main Video.
- Management should not be selectable as a media input/output route interface.
- Operator access to UI/Grafana will come through DMZ, while internal service communication remains on Management.
- Architect must decide whether UI/Grafana are bound directly on DMZ-facing IPs or exposed through a DMZ reverse proxy to management-bound services.
- UI route interface choices should be grouped as Main Video, Backup Video, and DMZ Video for now.
- Worker UDP publish IPs and port ranges must be configurable through env files.

## Core Workflows

Operators must be able to:

- Create a stream service.
- Select source protocol and fill only protocol-relevant fields.
- Configure destination output or HLS-only local output.
- Select target worker role: primary, backup, or all.
- Select video bind interfaces for primary and backup workers.
- Select route input/output interfaces by network zone: Main Video, Backup Video, or DMZ Video.
- Start, stop, edit, move, and delete services.
- See current status, active input, destination, worker target, preview, HLS links, and errors.

## Protocol Scope

Sources:

- SRT, using `Listener` and `Caller` modes. `Rendezvous` is deferred.
- UDP, with `Unicast` and `Multicast` type selection.
- RTMP
- RIST
- HLS

Destinations:

- SRT, using `Listener` and `Caller` modes. `Rendezvous` is deferred.
- UDP, with unicast/multicast-aware addressing where applicable.
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

## Route Editor V2 Requirements

Engineering feedback captured in `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf` adds the following product requirements for the next configuration slice:
The detailed product scope map is maintained in `docs/route-editor-v2-product-scope-map.md`.

- The create/edit experience should behave like a route editor with clear Source and Destination sections.
- The form should dynamically reveal fields based on protocol, protocol mode, and redundancy mode.
- Network/link parameters should be visually and conceptually separate from protocol parameters.
- Route basics should include route name, source, destination, start-on-create behavior, and destination start-on-route-start behavior where applicable.
- Source UDP should ask for UDP type, address, port, and relevant interface binding.
- Source SRT should ask for SRT mode, address/port semantics appropriate to listener or caller, latency, receive buffer, passphrase, Stream ID, and error correction where supported.
- Destination UDP should ask for interface, address, port, FEC, bitrate, traffic shaping, MTU, TTL, and ToS where supported.
- Destination SRT should ask for SRT mode, path redundancy mode, connection/caller limits when listener, interface/address/port rows, link parameters, latency, retransmission bandwidth, encryption, passphrase, authentication, RTP header, Stream ID, and error correction where supported.
- Path redundancy should add a secondary network path rather than overloading worker selection.
- Stream ID should support `default` builder mode and `custom` raw mode. Default mode should include host/mode, resource name, and username-style fields if confirmed by architecture.
- Destination Stream ID configuration should reuse the same product behavior as input Stream ID configuration.
- `TS over RTP` appears in the engineering reference UI but is not part of the current implemented product; Architect should explicitly add it to future-compatible schema or defer it.
- Future NIC IP configuration through Linux Netplan should be a separate Network administration feature with backup, validation, rollback, and permission controls.

## Operational Guardrails

- Full HLS remains capped at 24 hours of buffer.
- Full HLS service count is configurable and limited by default.
- HLS startup checks minimum free disk and optional storage quota settings.
- Generated HLS artifacts are cleaned on service stop.
- Operators should size CPU/GPU and storage for transcoding load before enabling many Full HLS services.

## Non-Goals For Current Slice

- Smart HLS passthrough/cache.
- Automatic failback.
- SRT `Rendezvous` mode.
- Write-capable Linux Netplan/NIC management inside Route Editor V2.
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

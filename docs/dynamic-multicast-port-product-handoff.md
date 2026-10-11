# Dynamic UDP Multicast Intake - Product Lead Handoff

## Goal

Allow broadcast operators to configure a UDP multicast source on any administrator-permitted source port from `1024-65535`, while preserving explicit interface selection, redundant workers, network-zone separation, and secure control-plane connectivity.

## Product Context

The Route Editor already lets an operator select UDP, choose Multicast, select an input interface, enter a multicast group, and enter a source port. The API accepts source ports up to `65535`, and FFmpeg uses the stored source port.

Production worker containers currently publish only container ports `9000-9010`. This means the saved product contract and the reachable deployment contract can disagree. A route configured on port `5500`, for example, can validate successfully but remain unreachable in the current production Compose deployment.

## Confirmed Requirements

- One UDP multicast service represents one multicast group and one source port.
- The operator selects the source interface from eligible Main Video, Backup Video, or DMZ Video inventory.
- Management is never selectable as a media source interface.
- The permitted source-port policy is `1024-65535`.
- The user should not be restricted to the current 11-port `9000-9010` window.
- Primary and backup workers may need to receive the same multicast group and port concurrently.
- The design must work for one physical server with two workers and for multi-server HA.
- Redis/Postgres remain Docker-internal on a single server or Management-only for multi-server HA; they must not be exposed to DMZ.
- Existing structured `source.primary_endpoint.port`, legacy `source_port`, interface inventory, and node-binding compatibility must be preserved.

## Product Safety Rules

- Reject source ports outside `1024-65535`.
- Reject or clearly manage conflicting worker/interface/group/port combinations.
- Reject startup when the selected port is not reachable under the active deployment configuration.
- Provide an actionable error rather than leaving a service indefinitely pending or repeatedly recovering.
- Do not silently remap the operator's selected source port. The sender-facing port and configured route port should match unless a clearly displayed compatibility mapping is intentionally retained.
- Temporary explicit Docker mappings may be used for engineering tests but must not be described as arbitrary-port production support.

## Architecture Questions To Resolve

1. Should Linux worker containers use host networking so FFmpeg binds selected ports directly on installed NICs?
2. Would dedicated macvlan/ipvlan media networks provide safer isolation while retaining a bridge/management path to Redis?
3. How will a worker access Main Video, Backup Video, and DMZ Video simultaneously under the selected container-network model?
4. How will Redis remain reachable securely when workers no longer rely only on the current Compose bridge?
5. What is the socket ownership key: worker plus interface plus group plus port, or interface plus group plus port across all workers?
6. Does concurrent primary/backup reception require FFmpeg `reuse=1`, multicast membership options, or kernel tuning?
7. How are host firewall rules and multicast routes provisioned without making firewall administration part of the Route Editor?
8. How will existing deployments migrate and roll back without interrupting unrelated API/Grafana services?

## Required Technical Plan

The Architect should provide:

- Selected worker network model and rationale.
- Single-server and multi-server topology diagrams or precise interface mappings.
- Compose/env changes and migration strategy.
- Redis/control-plane connectivity design.
- FFmpeg UDP multicast URL and socket option behavior.
- API/start validation and conflict-detection behavior.
- UI changes, if any, beyond the existing source port field.
- Observability and error messages for bind, join, route, and duplicate-port failures.
- Rollback plan to the current bounded port publication model.
- Dev Lead implementer handoff with files, sequencing, and verification.

## Verification Requirements

- Test ports `1024`, a representative middle port such as `5500`, and `65535`.
- Receive multicast on Main Video, Backup Video, and DMZ Video.
- Verify both primary and backup can receive the same group/port when required.
- Verify two different groups can use the same port on the same eligible interface when supported by the selected socket model.
- Verify duplicate/conflicting services are rejected or deliberately supported.
- Verify worker restart and desired-state reconciliation rejoin multicast correctly.
- Verify API/UI and Grafana remain reachable and Redis/Postgres remain off DMZ.
- Verify single-server and multi-server deployment configurations.
- Include a real FFmpeg multicast source and packet-level/receiver evidence; static Compose rendering alone is insufficient.

## Out Of Scope

- SRT Rendezvous.
- Automatic failback.
- Linux Netplan editing.
- UI-managed firewall configuration.
- General-purpose exposure of all host UDP ports.

## Handoff Output

Architect should update `docs/architecture.md`, refine backlog item 13, and prepare a Dev Lead handoff. Any unresolved question that materially affects security, multicast correctness, or single-server HA must be raised before implementation.

## Architecture Resolution

Architect selected Linux host networking for production worker containers, while retaining bridge networking for control-plane services. Workers will use a separate authenticated Redis endpoint, FFmpeg multicast input will use role-aware `localaddr` plus `reuse=1`, and different service IDs will not share one resolved bind IP and port in the first release. The implementation plan and Dev Lead review gates are in `docs/dynamic-multicast-port-architect-handoff.md`.

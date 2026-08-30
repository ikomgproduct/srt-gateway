# Route Editor V2 Product Scope Map

## Purpose

This file preserves the full product intent from the engineering feedback PDF and the Dev Lead review comments before Architect updates the implementer handoff.

Source feedback:

- `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf`

Active project:

- `C:\worklocal\ikoSRTgateway`

## Product Decision Summary

- SRT `Rendezvous` is deferred.
- Route Editor V2 should become a protocol-aware Source/Destination workflow.
- The first implementation slice should remain backend/API-focused, but the full product scope must stay visible for later UI and FFmpeg work.
- Network interface selection remains required for operators.
- Path redundancy is a route/network-path concept, not the same thing as worker primary/backup targeting.
- Linux Netplan write management is future scope and should become a separate Network Administration feature.

## Full Product Scope From Engineering Feedback

### Route Basics

The route editor should support:

- Route name.
- Source section.
- Destination section.
- Start once created behavior.
- Start once route starts behavior for destinations where applicable.
- Clear status visibility after route creation.

### Source Protocols

Source protocol options should include:

- `TS over UDP`
- `TS over SRT`
- `TS over RTP`
- `RIST`
- `RTMP`
- `HLS`

Product notes:

- Existing internal protocol value `udp` can represent `TS over UDP`.
- Existing internal protocol value `srt` can represent `TS over SRT`.
- Existing internal protocol value `rtmp` can represent `RTMP`.
- Existing internal protocol value `rist` can represent `RIST`.
- Existing internal protocol value `hls` can represent `HLS`.
- `TS over RTP` is visible in the engineering reference UI but is not yet implemented in the current product. Architect should decide whether to add it to the structured schema now as future-compatible, or explicitly defer it.

### Destination Protocols

Destination protocol options should include:

- `TS over UDP`
- `TS over SRT`
- `RTMP/RTMPS`
- `RIST`

Product notes:

- Generated HLS output remains separate from normal destinations.
- Raw destination URL may remain as an advanced compatibility option, but it should not be the primary operator workflow.
- Current runtime supports one normal destination. If multiple destination objects are accepted in the structured contract, Architect must define whether only the first enabled destination is active until multi-output runtime support is implemented.

### UDP Product Fields

UDP source/destination should support:

- Type: `Unicast` or `Multicast`.
- Network interface.
- Address.
- Port.
- Link parameters where applicable:
  - FEC.
  - Maximum bitrate.
  - Traffic shaping.
  - MTU.
  - TTL.
  - ToS.

### SRT Product Fields

SRT source/destination should support:

- Type/mode: `Listener` or `Caller`.
- Network interface.
- Address.
- Port.
- Path redundancy mode.
- Secondary interface/address/port when path redundancy is enabled.
- Latency.
- Receive buffer.
- Retransmission bandwidth.
- Encryption.
- Passphrase.
- Authentication.
- RTP header.
- Error correction method.
- Stream ID.
- Connection limit and number of callers for listener destinations where supported.

Deferred:

- SRT `Rendezvous`.

### Stream ID Product Behavior

Stream ID should support two modes:

- `Default`: structured builder.
- `Custom`: raw Stream ID text.

Default builder fields shown in the engineering reference include:

- Host and mode.
- Resource name.
- User name.

Architect should define the exact generated Stream ID template before Implementer derives the legacy `streamid` value. If the template is not confirmed, Implementer should persist/validate the structured object and only derive legacy `streamid` from `custom_value`.

### Path Redundancy

Path redundancy should:

- Be represented separately from `node_bindings`.
- Add a secondary interface/address/port row.
- Not change worker ownership by itself.
- Not imply automatic failover or automatic failback.

### Network Administration

The product request includes a future Network menu for managing server NIC settings.

Future feature should support:

- Viewing installed NICs.
- Editing interface IP settings.
- Persisting changes through Linux Netplan.

This must be separate from Route Editor V2 implementation because it can break server access. Before implementation it needs:

- Permission model.
- Configuration backup.
- Validation before apply.
- Rollback path.
- Operator confirmation.
- Management-interface protection.

## Included In Current Implementer Slice

Backlog item 8 should include:

- Structured schema models.
- Validation and normalization helpers.
- Legacy flat payload compatibility.
- Structured source/destination acceptance.
- Deriving compatibility fields where safe.
- Tests for schema and normalization.

Backlog item 8 should not include:

- Full UI rebuild.
- Full FFmpeg behavior expansion.
- Runtime path redundancy.
- Multi-destination FFmpeg output.
- Netplan/NIC write management.
- SRT `Rendezvous`.
- Automatic failback.

## Dev Lead Clarifications Needed Before Implementation

Architect should update the implementer handoff to clarify:

- Use `Field(default_factory=list)` for `destinations`.
- Define whether multiple submitted destinations are rejected or accepted but only the first enabled normal destination is used.
- Define Stream ID derivation behavior. If no exact default template is confirmed, only `custom_value` should derive legacy `streamid`.
- Name the normalization helper location so the Implementer does not scatter logic across API, frontend, and FFmpeg code.

## Suggested Product Order

1. Backend/API structured contract and normalization.
2. Dev Lead review of schema and compatibility behavior.
3. FFmpeg mapping for the normalized contract.
4. Protocol-aware UI for Source and Destination.
5. Stream ID builder UI.
6. Path redundancy UI and runtime behavior.
7. Network Administration discovery/design.

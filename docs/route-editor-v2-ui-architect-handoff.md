# Route Editor V2 UI Architect Handoff

## Goal

Implement backlog item 9: replace the current flat create/edit form with a protocol-aware Route Editor V2 UI that serializes the committed structured API contract while preserving legacy flat compatibility fields.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Source Context

- `.agent-context.md`
- `backlog/tasks.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `docs/route-editor-v2-product-scope-map.md`
- `docs/route-editor-v2-implementer-handoff.md`
- `docs/route-editor-v2-dev-lead-implementer-instructions.md`
- Current frontend files:
  - `frontend/index.html`
  - `frontend/app.js`
  - `frontend/style.css`
  - `tests/test_frontend_static.py`

## Current Shape

The backend/API structured contract is committed in backlog item 8.

Current UI behavior is still mostly flat:

- `frontend/index.html` has one create/edit modal with flat source fields and a destination URL builder.
- `frontend/app.js` submits legacy flat fields: `source_protocol`, `source_mode`, `source_ip`, `source_port`, `source_url`, `destination_url`, `node_bindings`, `hls_outputs`, and related advanced fields.
- The UI already fetches `/api/interfaces` and uses primary/backup input/output interface dropdowns for `node_bindings`.
- The UI already supports HLS source visibility and low/full HLS output controls.
- The UI does not yet serialize structured `source` or `destinations`.
- The UI does not yet hydrate structured `source` / `destinations` when editing services.
- The UI does not yet expose structured path redundancy or default/custom Stream ID controls.

## Proposed Change

Keep the existing modal and static frontend approach, but reorganize it into clear Route Editor sections:

- Basics
- Source
- Destination
- HLS Output
- Worker Target And Bindings
- Advanced / Compatibility

The implementation should remain incremental and avoid introducing a frontend framework.

The form should produce both:

- Structured Route Editor V2 fields: `source` and `destinations`
- Legacy flat compatibility fields required by current workers: `source_protocol`, `source_mode`, `source_ip`, `source_port`, `source_path`, `source_url`, `destination_url`, `latency_ms`, `passphrase`, `pbkeylen`, `streamid`, `node_bindings`, and HLS fields

The backend normalizer remains the source of truth for final compatibility derivation, but the UI should serialize predictable structured fields so edit round trips are durable.

## UI Behavior

### Source Section

Protocol selector:

- `srt`
- `udp`
- `rtmp`
- `rist`
- `hls`

Field visibility:

- SRT source:
  - Show mode: `listener` or `caller`.
  - Show primary endpoint fields: interface dropdown, address, port.
  - Show SRT parameters: latency, passphrase, encryption/authentication fields represented by the committed schema, and Stream ID controls.
  - Keep SRT key size (`pbkeylen`) as a top-level legacy compatibility field only; do not serialize it under `source.srt`.
  - Hide UDP type fields.
  - Hide HLS URL.
- UDP source:
  - Show type: `unicast` or `multicast`.
  - Show primary endpoint fields: interface dropdown, address, port.
  - Show link parameters where already captured or safe: TTL, MTU, ToS if implemented.
  - Hide SRT-only fields unless they remain in an advanced compatibility panel.
  - Hide HLS URL.
- RTMP source:
  - Show mode if current backend uses it.
  - Show address, port, and path.
  - Hide SRT Stream ID and UDP type.
- RIST source:
  - Show mode if current backend uses it.
  - Show address, port, latency/buffer-like field only if mapped to existing flat compatibility fields.
  - Hide SRT-specific Stream ID controls unless later architecture defines RIST-specific behavior.
- HLS source:
  - Show URL only.
  - Hide source port/address fields.

### Destination Section

Destination mode should support:

- Normal destination enabled with one selected destination protocol.
- HLS-only route when low-res or full HLS output is enabled and no normal destination is required.

Normal destination protocols:

- `srt`
- `udp`
- `rtmp`
- `rtmps`
- `rist`
- raw URL only as an advanced compatibility escape hatch

Field visibility:

- SRT destination:
  - Show mode: `caller` or `listener`.
  - Show primary endpoint: output interface dropdown, address, port.
  - Show path redundancy controls.
  - Show SRT parameters: latency, retransmission bandwidth, passphrase, authentication/encryption fields where represented by schema, RTP header/error correction as stored fields only unless FFmpeg mapping is confirmed.
  - Keep SRT key size (`pbkeylen`) as a top-level legacy compatibility field only; do not serialize it under `destinations[].srt`.
  - Show destination Stream ID controls using the same component logic as source Stream ID.
- UDP destination:
  - Show type: `unicast` or `multicast`.
  - Show primary endpoint: output interface dropdown, address, port.
  - Show link parameters: TTL, MTU, ToS, FEC, bitrate, traffic shaping where represented by schema.
  - Show path redundancy only if Product wants UDP path redundancy in UI; otherwise keep path redundancy to SRT destination for this slice.
- RTMP/RTMPS destination:
  - Show URL builder fields: protocol, host, port, app/path, stream key.
  - Do not show output bind interface as runtime-applied unless marked informational, because current FFmpeg builder does not apply bind IP to RTMP.
- RIST destination:
  - Show endpoint or URL fields conservatively.
  - Do not add unsupported advanced RIST behavior beyond the structured field storage.
- Raw URL:
  - Keep as advanced compatibility.
  - Require non-empty URL.
  - Do not show structured protocol controls.

Destination list behavior:

- Current runtime supports one enabled normal destination.
- The UI should submit at most one enabled destination object.
- Do not build multi-output UX in item 9.
- HLS outputs stay under `hls_outputs`, not `destinations`.

### Stream ID Component

Implement source and destination Stream ID with the same state shape:

```json
{
  "mode": "default",
  "host_mode": "publish",
  "resource_name": "resource",
  "username": ""
}
```

or:

```json
{
  "mode": "custom",
  "custom_value": "raw-stream-id"
}
```

Important compatibility rule:

- For `custom`, also populate legacy `streamid` for the current worker path.
- For `default`, persist structured fields but do not invent a legacy `streamid` until Product/Architect confirms the final template.

### Path Redundancy

Use the committed schema:

```json
{
  "enabled": true,
  "mode": "manual",
  "secondary_endpoint": {
    "interface_id": "backup-video-backup",
    "bind_ip": "10.71.15.3",
    "address": "192.0.2.20",
    "port": 9001
  }
}
```

UI rules:

- Default: disabled, `mode: none`, no secondary endpoint.
- When enabled: set `mode: manual` and require secondary endpoint address and port.
- Use interface dropdowns for secondary bind IP where applicable.
- Do not imply this changes worker primary/backup ownership; worker targeting remains `target_node`, `ha_mode`, and `failover_node`.

### Interface Dropdowns

Reuse `/api/interfaces`.

Rules:

- Source primary endpoint input bind should use interfaces filtered by input direction.
- Destination primary endpoint output bind should use interfaces filtered by output direction.
- Worker-role bindings remain the production runtime binding contract in `node_bindings.primary` and `node_bindings.backup`.
- Endpoint `interface_id` and `bind_ip` should be serialized into structured `source` / `destinations` for future mapping.
- Continue preserving unknown existing bind IPs as selectable "existing interface" options.

## Serialization Plan

Add small frontend helpers in `frontend/app.js`:

- `buildRouteEndpointFromForm(prefix)`
- `hydrateRouteEndpoint(prefix, endpoint, fallback)`
- `buildStreamIdConfig(scope)`
- `hydrateStreamIdConfig(scope, srtParams, legacyStreamid)`
- `buildSourceConfigFromForm()`
- `hydrateSourceConfig(config)`
- `buildDestinationConfigFromForm()`
- `hydrateDestinationConfig(config)`
- `buildLegacyFieldsFromStructured(source, destination)`
- `setRouteEditorVisibility()`

The submit payload should include both structured and flat fields:

```json
{
  "source": {},
  "destinations": [],
  "source_protocol": "srt",
  "source_mode": "listener",
  "source_ip": "0.0.0.0",
  "source_port": 9000,
  "source_url": null,
  "destination_url": "udp://239.10.10.10:5000"
}
```

Backend normalization will still run on create/update.

Important schema boundary:

- `pbkeylen` is not part of structured `SrtParameters` in backlog item 8.
- The UI may continue to expose SRT key size for current worker compatibility, but it must submit it only as the existing top-level `pbkeylen` field.
- Do not add `pbkeylen` to `source.srt` or `destinations[].srt` in item 9. Adding it to the structured API contract requires a separate backend/schema change.

## Edit Hydration

When editing:

1. Prefer structured `config.source` and first enabled `config.destinations[]` when present.
2. Fall back to legacy flat fields for old services.
3. Hydrate UI controls from the normalized state.
4. Preserve fields the UI does not display if possible, especially disabled extra destination objects, but do not submit more than one enabled normal destination.
5. Preserve existing `node_bindings` exactly unless the operator changes binding dropdowns.

## Files Likely Affected

- `frontend/index.html`
- `frontend/app.js`
- `frontend/style.css`
- `tests/test_frontend_static.py`
- `README.md`
- `UI_USER_GUIDE.md`
- `.agent-context.md`
- `backlog/tasks.md`
- `docs/architecture.md`

Avoid changing:

- `api/schemas.py`
- `api/main.py`
- `api/models.py`
- `api/route_normalizer.py`
- `backend/ffmpeg_builder.py`
- `worker/worker.py`
- Docker/compose/env files

Only touch backend code if implementation reveals a clear UI-blocking compatibility defect.

## Out Of Scope

- Multi-output runtime.
- Backend FFmpeg structured source/destination mapping.
- SRT Rendezvous.
- TS over RTP runnable support.
- Netplan/NIC write management.
- Automatic failback.
- Redis/Postgres HA redesign.
- Removing legacy flat fields or `worker_1` compatibility.

## Acceptance Criteria

- Create modal is organized into clear Source and Destination route-editor sections.
- Source protocol selection shows only relevant source fields.
- Destination protocol selection shows only relevant destination fields.
- UDP source/destination support unicast/multicast type controls.
- SRT source/destination support listener/caller controls.
- Source and destination SRT Stream ID controls support default/custom modes.
- Path redundancy UI uses `path_redundancy` and only requires secondary endpoint fields when enabled.
- Interface dropdowns use `/api/interfaces` and serialize endpoint `interface_id` / `bind_ip` plus existing `node_bindings`.
- Creating a service submits structured `source` and `destinations` plus legacy flat compatibility fields.
- Editing a legacy flat service hydrates the Route Editor V2 controls correctly.
- Editing a structured service hydrates from `source` / `destinations` and round-trips without dropping structured data the UI owns.
- HLS-only behavior remains unchanged: destination can be omitted only when low-res or full HLS output is enabled.
- Existing frontend static tests pass and new Route Editor V2 static tests cover markup, visibility helpers, serialization helpers, and edit hydration helper names/paths.

## Verification Plan

1. Run frontend/static checks:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest tests/test_frontend_static.py
```

2. Run Route Editor V2 backend contract checks:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest tests/test_route_editor_v2_contract.py
```

3. Run full regression:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
```

4. Manual browser QA:

- Open create modal.
- Switch source protocol through SRT, UDP, RTMP, RIST, HLS and confirm irrelevant fields hide.
- Switch destination protocol through SRT, UDP, RTMP, RTMPS, RIST, raw and confirm irrelevant fields hide.
- Create disabled test payloads through the UI for SRT and UDP paths and inspect API response.
- Edit an existing legacy flat service and confirm values hydrate into the new controls.
- Edit an existing structured service and confirm structured `source` / `destinations` round-trip.
- Confirm destination is required when no HLS output is enabled and optional when HLS output is enabled.

## Repo-State Caveat

At handoff time, `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf` is staged. Confirm whether the team wants that PDF committed before starting item 9 changes, so the next commit does not accidentally mix source-reference archival with UI implementation.

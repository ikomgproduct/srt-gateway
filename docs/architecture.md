# SRT Gateway Architecture

## System Shape

SRT Gateway is split into a control plane and worker runtime.

Control plane:

- FastAPI API in `api/main.py`.
- Pydantic API schemas in `api/schemas.py`.
- SQLAlchemy service persistence in `api/models.py`.
- Static frontend served from `frontend/`.
- Redis desired config, commands, metrics cache, heartbeats, and leases.
- Interface inventory endpoint `/api/interfaces`, backed by `INTERFACE_INVENTORY_JSON` or built-in defaults.

Worker runtime:

- Microservice worker in `worker/worker.py`.
- FFmpeg command construction in `backend/ffmpeg_builder.py`.
- Runtime service models in `backend/models.py`.
- Legacy standalone stream manager in `backend/stream_manager.py`.

Observability:

- Redis metrics cache and Pub/Sub telemetry.
- Prometheus/Grafana compose services.
- Preview thumbnails and HLS playlists written under `frontend/previews/<service_id>/`.
- Production deployments mount that preview path from `PREVIEW_STORAGE`; multi-server HA must use shared storage mounted on all participating hosts.

## Data Flow

1. Operator creates or edits a service through the frontend.
2. Frontend sends JSON to `/api/services`.
3. API validates using `ServiceConfigRequest`.
4. API persists service config to Postgres.
5. API writes desired config to Redis hash `service_configs`.
6. API publishes commands on Redis channel `stream_commands`.
7. Workers receive commands and also reconcile periodically from `service_configs`.
8. Eligible worker builds input URL and FFmpeg command.
9. Worker starts FFmpeg and publishes metrics/status.
10. UI polls `/api/services` for config plus live state.

## Redis Usage

Keys/channels:

- `service_configs`: Redis hash of desired service config by service ID.
- `stream_commands`: Pub/Sub channel for start/stop commands.
- `worker_heartbeat:<role>`: heartbeat key per worker role.
- `stream_lease:<service_id>`: active/passive ownership lease.
- `stream_metrics_cache`: Redis hash of latest service status/metrics.
- `telemetry_metrics`: Pub/Sub channel for service telemetry.
- `telemetry_hardware`: Pub/Sub channel for hardware telemetry.

## Service Contract

Important fields:

- `source_protocol`: `srt`, `udp`, `rtmp`, `rist`, or `hls`.
- `source_ip` and `source_port`: network source fields for non-HLS protocols.
- `source_url`: required for HLS source.
- `destination_url`: normal output URL, optional only when HLS output is enabled.
- `target_node`: preferred worker role.
- `ha_mode`: `manual`, `active_passive`, or `active_active`.
- `failover_node`: passive role for active/passive services.
- `node_bindings`: per-role input/output bind IPs.
- `enable_hls_preview`: compatibility flag for low-res HLS output.
- `hls_outputs`: structured low/full HLS output profiles.
- `source`: optional Route Editor V2 structured source object.
- `destinations`: optional Route Editor V2 structured destination list.

## Route Editor V2 Contract Direction

Engineering feedback in `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf` should drive a future protocol-aware route contract. The current flat compatibility fields should remain supported during migration, but new UI/API work should move toward structured source and destination configuration.

Architectural targets:

- Keep SRT `Rendezvous` out of scope for now; support SRT `Listener` and `Caller`.
- Model source and destination as protocol-specific objects rather than only a single `destination_url`.
- Keep legacy flat fields compatible for existing services and lab use.
- Separate network/link parameters from protocol parameters.
- Represent interface/address/port as path endpoints that can be reused by UDP, SRT, and future protocols.
- Represent path redundancy explicitly as an optional secondary endpoint row.
- Represent SRT Stream ID as a structured object with `default` and `custom` modes.
- Reuse the same Stream ID object for SRT input and SRT destination.
- Keep worker role targeting separate from network path redundancy; primary/backup worker ownership and primary/backup network paths are related but not the same contract.

Possible future shape:

```json
{
  "source": {
    "protocol": "srt",
    "mode": "listener",
    "primary_endpoint": {
      "interface_id": "primary-video-main",
      "bind_ip": "10.70.15.3",
      "address": "0.0.0.0",
      "port": 9000
    },
    "path_redundancy": {
      "enabled": false,
      "mode": "none",
      "secondary_endpoint": null
    },
    "srt": {
      "latency_ms": 125,
      "receive_buffer_bytes": 10240,
      "passphrase": "",
      "error_correction": "arq",
      "stream_id": {
        "mode": "default",
        "resource_name": "resource",
        "username": ""
      }
    }
  },
  "destinations": [
    {
      "protocol": "udp",
      "type": "unicast",
      "primary_endpoint": {
        "interface_id": "primary-video-main",
        "bind_ip": "10.70.15.3",
        "address": "239.10.10.10",
        "port": 5000
      }
    }
  ]
}
```

This shape is implemented as an additive API/backend contract and the browser UI now submits this structure while preserving legacy flat fields. Broader FFmpeg/runtime mapping remains future work.

### Route Editor V2 Technical Plan

Current shape:

- `ServiceConfigRequest` in `api/schemas.py` preserves flat fields and also accepts structured `source` and `destinations`.
- HLS output and node bindings are already structured.
- `backend/ffmpeg_builder.py` builds input URLs from flat source fields and emits a single normal destination URL plus preview/HLS outputs.
- `frontend/app.js` serializes the Route Editor V2 form into structured `source` and one enabled normal `destinations[]` object, while also submitting legacy flat compatibility fields for the current worker path.

Proposed change:

- Structured route objects were added to the API contract without removing existing flat fields.
- Existing services remain valid and Redis/Postgres configs keep worker-compatible flat fields.
- `api/route_normalizer.py` normalizes flat and structured payloads at the API boundary before persistence and Redis sync.
- Keep the frontend protocol-specific form state, structured serialization, and legacy compatibility serialization aligned during the transition.

Files likely affected:

- `api/schemas.py`: add structured Pydantic models and compatibility validation.
- `api/main.py`: normalize create/edit payloads and preserve old response behavior.
- `api/route_normalizer.py`: hold pure structured-to-flat and flat-to-normalized conversion helpers.
- `api/models.py`: confirm JSON config persistence can hold the structured objects without migration; add DB migration only if columns are added.
- `backend/models.py`: mirror new runtime config models or accept structured dictionaries safely.
- `backend/ffmpeg_builder.py`: build input and output URLs from normalized endpoints/protocol params.
- `worker/worker.py`: ensure workers reconcile structured configs and lease ownership exactly as today.
- `frontend/index.html`: add protocol-aware source/destination sections and Stream ID controls.
- `frontend/app.js`: add field visibility, structured serialization, legacy derivation, and edit hydration.
- `frontend/style.css`: keep Route Editor V2 readable with wider grouped sections.
- `tests/`: add schema, builder, worker compatibility, and frontend static/serialization coverage.

Data and interfaces:

- `RouteEndpoint`: `interface_id`, `bind_ip`, `address`, `port`.
- `PathRedundancy`: `enabled`, `mode`, `secondary_endpoint`.
- `LinkParameters`: `mtu`, `ttl`, `tos`, `fec`, `max_bitrate_kbps`, `traffic_shaping`.
- `SrtParameters`: `latency_ms`, `receive_buffer_bytes`, `retransmission_bandwidth_kbps`, `encryption`, `passphrase`, `authentication`, `rtp_header`, `error_correction`, `stream_id`.
- `StreamIdConfig`: `mode: default|custom`, `host_mode`, `resource_name`, `username`, `custom_value`.
- `SourceConfig`: protocol-specific object for UDP, SRT, RTMP, RIST, or HLS.
- `DestinationConfig`: list-ready protocol-specific object for UDP, SRT, RTMP/RTMPS, RIST, or generated HLS-adjacent outputs. The list is future-compatible; current runtime should reject more than one enabled normal destination until multi-output behavior is implemented.

Compatibility behavior:

- Accept legacy flat payloads exactly as today.
- Accept new structured payloads and derive legacy flat fields for older worker/build paths until the worker is fully normalized.
- Return both structured fields and flat fields during the transition so the current UI, API clients, and tests remain stable.
- Keep `local_bind_ip`, `backup_input_ip`, and `worker_1` accepted for lab/legacy use, but do not expose them as the production UI target.
- Keep `node_bindings.primary` and `node_bindings.backup` as worker-role binding; do not overload them with path redundancy.
- For custom Stream ID mode, derive legacy `streamid` from `custom_value`.
- For default Stream ID mode, persist the structured fields but do not derive a legacy `streamid` until the exact template is confirmed.
- `TS over RTP` remains product-captured but deferred from runnable service API acceptance in the first structured-contract slice.

Current implementation notes:

- `source` and `destinations` are persisted as JSON columns.
- PostgreSQL startup bootstrap adds `source JSONB` and `destinations JSONB` if missing.
- More than one enabled normal destination is rejected until multi-output runtime behavior is implemented.
- Enabled structured destinations must include a usable URL or primary endpoint; empty `raw` destinations are rejected instead of producing an empty legacy `destination_url`.
- Enabled path redundancy requires `mode: manual` and a secondary endpoint with a port; it is persisted for the contract but does not change worker targeting yet.
- Structured HLS source derives `source_protocol=hls`, `source_url`, and `source_port=None`.
- Structured SRT/UDP source and destination payloads derive flat compatibility fields.
- Existing flat payloads are normalized into structured objects for API response and Redis desired config.
- The Route Editor V2 UI hydrates structured `source` / `destinations` first and falls back to legacy flat fields for existing services.
- `pbkeylen` remains top-level legacy compatibility only. It is intentionally not part of structured `SrtParameters` and must not be serialized inside `source.srt` or `destinations[].srt` without a separate schema change.

FFmpeg mapping:

- SRT listener input: listener host comes from selected input bind IP; `mode=listener`.
- SRT caller input: remote address/port come from endpoint address/port; selected input bind IP becomes `localaddr`.
- SRT destination listener: output bind IP/listener endpoint becomes listener host; `mode=listener`; listener-specific limits should only be applied when supported by FFmpeg/SRT URL params.
- SRT destination caller: remote address/port come from destination endpoint; output bind IP becomes `localaddr`.
- UDP input: address/port come from source endpoint; selected input bind IP becomes `localaddr`; multicast-specific options should be explicit and tested.
- UDP destination: address/port come from destination endpoint; output bind IP becomes `localaddr`; link parameters such as TTL and packet size map to URL params where FFmpeg supports them.
- RTMP/RTMPS destination: continue using `-f flv`; interface binding is not applied unless a future supported mechanism is proven.
- RIST: keep current behavior first; add richer fields only after confirming FFmpeg option mapping.
- HLS source and generated HLS output keep the current HLS architecture and guardrails.

Incremental implementation order:

1. Add schema models and normalization helpers with tests; no UI behavior change.
2. Add backend FFmpeg builder support for normalized source/destination while preserving flat behavior.
3. Add frontend Route Editor V2 sections for UDP and SRT source/destination. Done.
4. Add Stream ID builder and edit hydration. Done.
5. Add path redundancy UI/API behavior. UI and API persistence done; runtime failover behavior remains future work.
6. Add regression tests and QA scenarios using sample FFmpeg sources.
7. Update README/UI guide after behavior is implemented and reviewed.

Out of scope for Route Editor V2:

- SRT `Rendezvous`.
- Write-capable Linux Netplan/NIC configuration.
- Automatic failback.
- Redis/Postgres HA redesign.
- Removing legacy flat API compatibility.

## Binding Model

Current backend target:

```json
{
  "node_bindings": {
    "primary": {
      "input_bind_ip": "10.70.15.3",
      "output_bind_ip": "10.70.15.3"
    },
    "backup": {
      "input_bind_ip": "10.71.15.3",
      "output_bind_ip": "10.71.15.3"
    }
  }
}
```

Binding behavior:

- SRT listener uses input bind IP as listener host.
- SRT caller uses input bind IP as `localaddr`.
- UDP source uses input bind IP as `localaddr`.
- SRT/UDP destinations use output bind IP as `localaddr`.
- RTMP destination does not use output bind IP.
- Missing role-specific binding falls back to legacy `local_bind_ip`.

Interface inventory:

- The UI fetches `/api/interfaces`.
- Primary/backup input/output binding controls are dropdowns.
- Worker binding dropdown options are filtered by role and direction.
- Route source/destination dropdown options are filtered by video purpose and direction, excluding Management.
- Built-in defaults map Main Video to `10.70.15.3`, Backup Video to `10.71.15.3`, DMZ Video to `10.75.51.40`, and Management to `10.75.15.3`; production can override with `INTERFACE_INVENTORY_JSON`.
- `/api/interfaces` normalizes legacy inventory entries by filling `zone`, `purpose`, `network`, `node_roles`, and `directions`.

## Network Zone Direction

Product has confirmed a site-standard network-zone model for the next architecture cycle. The durable handoff is in `docs/network-zone-product-handoff.md`, and the Architect-to-Dev-Lead handoff is in `docs/network-zone-architect-handoff.md`.

Target zones:

- Main Video: `eno1`, `10.70.15.3`, internal video input/output.
- Backup Video: `eno2`, `10.71.15.3`, internal video input/output.
- DMZ Video: `eno3`, `10.75.51.40`, public/external video input/output.
- Management: `eno4`, `10.75.15.3`, API, SSH, Grafana/admin, and internal control-plane communication.

Architecture direction:

- Separate worker role, network zone, and route direction.
- Route endpoint dropdowns should filter by video purpose and input/output direction, not only by worker role.
- Management must not appear as a media route endpoint.
- DMZ Video must be selectable for input and output on both primary and backup workers.
- Main Video and Backup Video should pair as internal redundant paths.
- Production compose should support env-configurable worker UDP publishing across the required video IPs and port ranges.
- `docker-compose.production.video-zones.yml` is the explicit optional override for publishing worker UDP ports on DMZ Video in addition to the base internal video bindings.
- Direct DMZ bind support for UI/Grafana may remain for the current deployment, but Redis/Postgres must not be exposed to DMZ. A DMZ reverse proxy to management-bound services remains the safer future pattern.

## HLS Architecture

HLS output is local generated output.

Low-res profile:

- 360p
- 480p
- short rolling buffer, currently 10 seconds

Full profile:

- 720p
- 1080p
- configurable buffer up to 24 hours

Current implementation generates rendition playlists and local master playlists under:

```text
frontend/previews/<service_id>/low_res/
frontend/previews/<service_id>/full_res/
```

Known architecture gaps:

- Smart HLS input passthrough/cache is future work.

Guardrails:

- `MAX_FULL_HLS_SERVICES` limits active Full HLS services.
- Disabled Full HLS service templates do not consume `MAX_FULL_HLS_SERVICES` capacity until start or enable time.
- `/api/services/{id}/start` validates Full HLS capacity before marking a service enabled.
- `HLS_MIN_FREE_BYTES` enforces a minimum free-space check before HLS startup.
- `HLS_STORAGE_QUOTA_BYTES` optionally blocks estimated HLS storage above a configured quota.
- Generated `low_res` and `full_res` directories are removed on service stop.
- Master playlists avoid hard-coded `RESOLUTION` metadata because FFmpeg dynamically scales width.

## Deployment Strategy

- Keep production compose separate as `docker-compose.production.yml`.
- Use `docker-compose.production.yml` as the canonical production file for single-server and multi-server HA.
- Select deployment shape with env files and profiles:
  - single server: `local-state,control-plane,primary-worker,backup-worker`
  - control plane: `local-state,control-plane` or `control-plane` with external state
  - primary worker: `primary-worker`
  - backup worker: `backup-worker`
- Do not overwrite server-local `docker-compose-microservices.yml` without explicit approval.
- Bind API/UI and Grafana only to management IPs.
- Keep Redis/Postgres internal for single-server deployments.
- Expose Redis/Postgres on management network only when multi-server HA requires it.
- Production preview/HLS storage is selected with `PREVIEW_STORAGE`; named volume `shared_previews` is suitable for single-server, while multi-server requires a real shared filesystem path.
- Production compose carries explicit `MAX_FULL_HLS_SERVICES`, `HLS_MIN_FREE_BYTES`, and `HLS_STORAGE_QUOTA_BYTES` defaults.
- Older compose files are lab/legacy paths and are labelled as such.

## Testing

Preferred verification command:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
```

Host Python may not be installed, so container-based tests are preferred.

Important coverage areas:

- API validation for service contract compatibility.
- FFmpeg builder command behavior by protocol.
- Frontend static tests for expected controls and serialization paths.
- Worker routing and active/passive targeting.
- Legacy `StreamManager` node-role propagation into FFmpeg command building.

Last verified result after API image rebuild and installing `requirements-test.txt` in the running API container: `79 passed` with no pytest warning summary.

Latest production compose validation rendered successfully for single-server, control-plane, primary-worker, and backup-worker env examples.

## Operational Caveats

- Full HLS can consume significant CPU/GPU and disk.
- Redis/Postgres are critical control-plane dependencies.
- Manual failback is safer than automatic failback until guarded.
- UI must avoid implying target binding is the active lease owner.
- Existing compose passwords and exposed ports must be hardened for production.

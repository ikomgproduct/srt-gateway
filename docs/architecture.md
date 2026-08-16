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
- Dropdown options are filtered by role and direction.
- Built-in defaults map primary to `10.70.15.3` and backup to `10.71.15.3`; production can override with `INTERFACE_INVENTORY_JSON`.

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
- Disabled Full HLS service templates do not consume `MAX_FULL_HLS_SERVICES` capacity.
- `HLS_MIN_FREE_BYTES` enforces a minimum free-space check before HLS startup.
- `HLS_STORAGE_QUOTA_BYTES` optionally blocks estimated HLS storage above a configured quota.
- Generated `low_res` and `full_res` directories are removed on service stop.
- Master playlists avoid hard-coded `RESOLUTION` metadata because FFmpeg dynamically scales width.

## Deployment Strategy

- Keep production compose separate as `docker-compose.production.yml`.
- Do not overwrite server-local `docker-compose-microservices.yml` without explicit approval.
- Bind API/UI and Grafana only to management IPs.
- Keep Redis/Postgres internal for single-server deployments.
- Expose Redis/Postgres on management network only when multi-server HA requires it.

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

Last verified result after rebuild: `55 passed` with no pytest warning summary.

## Operational Caveats

- Full HLS can consume significant CPU/GPU and disk.
- Redis/Postgres are critical control-plane dependencies.
- Manual failback is safer than automatic failback until guarded.
- UI must avoid implying target binding is the active lease owner.
- Existing compose passwords and exposed ports must be hardened for production.

# SRT Gateway

SRT Gateway is a web-managed stream routing gateway for SRT, UDP, RTMP, RIST, and HLS sources. It runs FFmpeg pipelines from service definitions, exposes a browser UI/API, publishes metrics, and supports worker-node redundancy for broadcast-style deployments.

## What It Does

- Creates and manages stream routing services from a web UI or REST API.
- Supports SRT, UDP, RTMP, RIST, and HLS inputs.
- Supports SRT, UDP, RTMP/RTMPS, and RIST destinations.
- Runs FFmpeg workers separately from the API in microservice deployments.
- Publishes runtime state through Redis and Prometheus-compatible telemetry.
- Supports active/passive worker ownership with Redis leases.
- Supports separate management and video networks with per-node video bind IPs.
- Generates preview thumbnails and optional HLS preview output.

## Architecture

There are two main operating modes.

### Standalone Mode

One container runs the API, frontend, metrics endpoint, and stream manager together.

Use this for:

- simple single-node deployments
- quick testing
- legacy config-file based operation

Compose files:

- `docker-compose-standalone.yml`
- `docker-compose-gpu-standalone.yml`
- `docker-compose.yml` for a primary/backup standalone pair on one Docker host
- `docker-compose-gpu.yml`

These files are legacy/lab-oriented. Production HA should use `docker-compose.production.yml`.

### Microservices Mode

The API, workers, telemetry, Redis, Postgres, Prometheus, and Grafana run as separate services.

Use this for:

- production-style deployments
- active/passive worker redundancy
- two physical servers
- one physical server with two redundant workers

Compose files:

- `docker-compose.production.yml` for production layouts with explicit API/Grafana bind IPs and primary/backup worker profiles
- `docker-compose-microservices.yml` for local/lab testing
- `docker-compose-microservices-ha.yml` for legacy/lab HA testing
- `docker-compose-microservices-gpu.yml` for legacy/lab GPU testing

Recommended production direction: **microservices mode with `docker-compose.production.yml`**.

## Network Model

Recommended facility layout:

- **Main Video:** internal video input/output, for example `eno1 / 10.70.15.3`.
- **Backup Video:** internal backup video input/output, for example `eno2 / 10.71.15.3`.
- **DMZ Video:** external/public video input/output, for example `eno3 / 10.75.51.40`.
- **Management:** API, SSH, Grafana/admin, Redis/Postgres access, worker heartbeats, leases, and telemetry, for example `eno4 / 10.75.15.3`.

Keep control traffic and media traffic separated where possible.
Management interfaces must not be selected as media route endpoints. DMZ Video is a media network and may be selected for source input or destination output.

### Management Network

These values should use management-network DNS/IPs:

- `DATABASE_URL`
- `REDIS_URL`
- worker heartbeat and lease traffic

Current production examples bind API/UI and Grafana to explicit operator-facing IPs through `API_BIND_IP`, `GRAFANA_BIND_IP`, and `GRAFANA_ALT_BIND_IP`. In the site examples, API/UI is directly DMZ-accessible on `10.75.51.40:8000`, while Grafana is bound on both `10.75.15.3:4000` and `10.75.51.40:4000`. Redis/Postgres must not be exposed to DMZ; keep them Docker-internal for single-server or management-network-only for multi-server HA.

A future hardening option is to bind API/UI and Grafana only on Management and expose them through a DMZ reverse proxy.

### Video Network

Media binding is controlled by service configuration.

Legacy/default field:

```json
{
  "local_bind_ip": "10.50.1.21"
}
```

Per-node field for redundant installations:

```json
{
  "node_bindings": {
    "primary": {
      "input_bind_ip": "10.50.1.21",
      "output_bind_ip": "10.50.1.21"
    },
    "backup": {
      "input_bind_ip": "10.50.1.22",
      "output_bind_ip": "10.50.1.22"
    }
  }
}
```

When the `primary` node owns the service, FFmpeg uses the primary binding. When the `backup` node owns the service, FFmpeg uses the backup binding.

If `node_bindings` does not contain the active node, the system falls back to legacy `local_bind_ip`. New services should prefer explicit input/output bindings.

The UI populates primary/backup input/output binding dropdowns from `/api/interfaces`. Production deployments can override the built-in interface list with `INTERFACE_INVENTORY_JSON`.

Route source and destination interface dropdowns are zone-aware. They show video interfaces that match the route direction and exclude Management. Worker binding dropdowns remain role-aware for primary/backup compatibility.

`INTERFACE_INVENTORY_JSON` controls what the UI/API exposes as selectable route interfaces. Production workers use host networking and bind the selected inventory IP directly; the optional video-zone override is retained only as an empty one-release compatibility file.

## Redundancy Model

The active/passive implementation is based on Redis heartbeats and per-service leases.

Each worker has a `NODE_ROLE`, such as:

- `primary`
- `backup`

Legacy/lab workers may still use names such as `worker_1`, but production services should target `primary`, `backup`, or `all`.

Each service can define:

- `ha_mode`
- `target_node`
- `failover_node`
- `failover_after_seconds`
- `failback_policy`

### Active/Passive Behavior

For a service like:

```json
{
  "ha_mode": "active_passive",
  "target_node": "primary",
  "failover_node": "backup",
  "failover_after_seconds": 15,
  "failback_policy": "manual"
}
```

Normal state:

- `primary` heartbeats to Redis.
- `primary` claims the service lease.
- `primary` starts FFmpeg.
- `backup` sees `primary` is healthy and stays passive.

Failure state:

- `primary` stops heartbeating.
- after the lease/heartbeat timeout, `backup` claims the service lease.
- `backup` starts FFmpeg using its own node-specific video bind IP.

Failback:

- default policy is manual.
- when `primary` comes back, it does not immediately steal the stream back.
- this avoids stream flapping.

## Deployment Options

### Which Production Compose File To Use

For every new production or production-like installation, use only:

```text
docker-compose.production.yml
```

`docker-compose.production.yml` is the canonical deployment definition for
both supported hardware layouts. `COMPOSE_PROFILES` in the selected environment
file determines which services run on that host.

| Installation | Environment template | Enabled profiles |
| --- | --- | --- |
| One server, two workers | `.env.production.single-server.example` | `local-state,control-plane,primary-worker,backup-worker` |
| Multi-server control plane | `.env.production.control-plane.example` | `local-state,control-plane` by default |
| Multi-server primary worker | `.env.production.primary.example` | `primary-worker` |
| Multi-server backup worker | `.env.production.backup.example` | `backup-worker` |

`docker-compose.production.video-zones.yml` is **not an additional production
topology and is not required for a new installation**. It is an empty,
one-release compatibility override retained only for servers or scripts that
still use the former two-file command. This old command remains valid but has
the same effective configuration as the canonical one-file command:

```bash
sudo docker compose --env-file .env.production.single-server.local \
  -f docker-compose.production.yml \
  -f docker-compose.production.video-zones.yml \
  up -d --build
```

Do not add interface addresses, port ranges, or services to the compatibility
file. Configure media interfaces through `INTERFACE_INVENTORY_JSON`; production
workers use Linux host networking and bind the selected host IP and service
port directly. The compatibility file is planned for removal after the
migration window.

### Prepare A Server-Local Environment File

Do not run production from a committed `.example` file. Copy the template for
the host, edit the `.local` copy, and keep that copy server-local:

```bash
# Single-server HA
cp .env.production.single-server.example .env.production.single-server.local
chmod 600 .env.production.single-server.local

# Multi-server: run only the matching copy command on each host
cp .env.production.control-plane.example .env.production.control-plane.local
cp .env.production.primary.example .env.production.primary.local
cp .env.production.backup.example .env.production.backup.local
```

Files matching `.env.production.*.local` are excluded from Git and the Docker
build context. Preserve them separately before replacing a checkout or server.

Required configuration:

| Variable | Purpose |
| --- | --- |
| `COMPOSE_PROFILES` | Selects the services for this host. Use the profile combinations in the table above. |
| `API_BIND_IP` | Host IP for API/UI TCP port `8000`; current site design uses the DMZ-facing operator IP. |
| `GRAFANA_BIND_IP`, `GRAFANA_ALT_BIND_IP` | Host IPs for Grafana TCP port `4000`. Both values must exist on a single host when both mappings are enabled. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Database credentials and API connection. Replace every `change-me` value. |
| `REDIS_PASSWORD`, `REDIS_BIND_IP`, `REDIS_PORT`, `REDIS_URL` | Redis authentication, publication, and control-plane connection. Use loopback on one server or Management on multiple servers. |
| `WORKER_REDIS_URL` | Authenticated Redis URL used by host-network workers. It cannot use the Docker service name from the host network. |
| `UDP_MULTICAST_PORT_MIN`, `UDP_MULTICAST_PORT_MAX` | Administrator-approved multicast source-port policy. Default: `1024-65535`. These values do not edit the host firewall. |
| `INTERFACE_INVENTORY_JSON` | NIC/IP inventory shown in route and worker binding dropdowns. Management entries must have no media directions or worker roles. |
| `PREVIEW_STORAGE` | Named volume for one server or a shared filesystem path mounted identically on all multi-server hosts. |
| `MAX_FULL_HLS_SERVICES`, `HLS_MIN_FREE_BYTES`, `HLS_STORAGE_QUOTA_BYTES` | Full-HLS capacity and storage guardrails. |
| `GRAFANA_ADMIN_PASSWORD` | Required Grafana administrator password. Replace `change-me`. |

The old `PRIMARY_VIDEO_IP`, `BACKUP_VIDEO_IP`, `PRIMARY_PORT_RANGE`, and
`BACKUP_PORT_RANGE` variables do not control the current host-network workers
and should not be added to new production env files.

Before starting containers, validate the rendered configuration:

```bash
sudo docker compose --env-file .env.production.single-server.local \
  -f docker-compose.production.yml config --quiet
```

After any environment-file change, recreate the affected services so the new
values and host bindings take effect:

```bash
sudo docker compose --env-file .env.production.single-server.local \
  -f docker-compose.production.yml up -d --build --force-recreate
```

### Option 1: Multi-Server HA

Recommended for facility redundancy.

Control-plane/state host:

- API/UI
- telemetry
- Prometheus/Grafana
- Redis/Postgres, or connections to external Redis/Postgres
- shared preview/HLS storage mounted at the same path used by workers

Primary worker host:

- worker with `NODE_ROLE=primary`
- video input/output bound to the primary video interface

Backup worker host:

- worker with `NODE_ROLE=backup`
- video input/output bound to the backup video interface

Run the control plane:

```bash
sudo docker compose --env-file .env.production.control-plane.local -f docker-compose.production.yml up -d --build
```

The control-plane example includes `local-state` when this host owns Redis/Postgres. If Redis/Postgres are external or managed separately, remove `local-state` from `COMPOSE_PROFILES` and set `DATABASE_URL` / `REDIS_URL` to the management-network addresses.

Run the primary worker host:

```bash
sudo docker compose --env-file .env.production.primary.local -f docker-compose.production.yml up -d --build
```

Run the backup worker host:

```bash
sudo docker compose --env-file .env.production.backup.local -f docker-compose.production.yml up -d --build
```

Production workers use Linux host networking and can bind directly to eligible Main Video, Backup Video, and DMZ Video addresses. The former video-zone override is no longer required; it remains as an empty compatibility file for one release.

Multi-server requirements:

- `WORKER_REDIS_URL` must point to an authenticated Redis instance reachable on the management network.
- `REDIS_URL` is the authenticated bridge/control-plane URL used by API and telemetry.
- `DATABASE_URL` must point to a Postgres instance reachable by the API.
- `PREVIEW_STORAGE` must be a shared filesystem path mounted on the control-plane and worker hosts, for example `/mnt/srt-gateway/previews`.
- The shared preview path is required for UI thumbnails and HLS playlists generated by workers.
- Use `INTERFACE_INVENTORY_JSON` so the UI dropdowns match the installed hardware.

### Option 2: Single-Server HA

Use `docker-compose.production.yml` with all production profiles enabled.

This starts:

- `worker-primary`
- `worker-backup`
- API
- Redis
- Postgres
- telemetry
- Prometheus
- Grafana

Run:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml up -d --build
```

This default layout binds:

```text
API/UI:         10.75.51.40:8000
Grafana:        10.75.15.3:4000 and 10.75.51.40:4000
worker-primary: Linux host network; selected video IP and service UDP port
worker-backup:  Linux host network; selected video IP and service UDP port
Redis:         127.0.0.1:6379 with authentication
```

UDP multicast sources may use an administrator-approved port from `1024-65535`. FFmpeg binds only the configured service port and interface; Compose does not reserve or publish the full range. Different service IDs cannot use the same input bind IP and port while enabled.

Single-server mode publishes authenticated Redis on loopback for host-network workers, keeps Postgres Docker-internal, and uses the Docker named volume `shared_previews` for previews/HLS.

### Host-Network And Redis Migration

Production host-network workers require Linux. Before upgrading, verify every inventory IP exists on the intended worker host, allow the configured UDP multicast policy through the host firewall, and confirm the switches permit IGMP membership on Main Video, Backup Video, and DMZ Video.

1. Copy the matching `.env.production.*.example` to your server-local env file without overwriting local addresses or credentials.
2. Add `REDIS_PASSWORD`, authenticated `REDIS_URL`, authenticated `WORKER_REDIS_URL`, `REDIS_BIND_IP`, `REDIS_PORT`, and `UDP_MULTICAST_PORT_MIN/MAX`.
3. On a single server, use loopback for `REDIS_BIND_IP` and `WORKER_REDIS_URL`. For multiple servers, use the firewall-restricted Management IP.
4. Recreate Redis, API, telemetry, and both workers together so Redis authentication and clients change atomically.
5. Verify `/api/runtime-policy`, `/api/workers`, worker heartbeats, and a real multicast source before enabling production routes.

Rollback requires the prior release's Compose and matching env file, including its bounded worker port mappings and unauthenticated Redis URLs. Stop the current stack before restoring that complete set; do not mix old clients with authenticated Redis or host-network workers.

### Lab And Legacy Compose Files

The older compose files remain for local testing and compatibility:

- `docker-compose-microservices.yml`: local one-worker lab stack.
- `docker-compose-microservices-ha.yml`: legacy local HA stack with shifted backup UDP ports.
- `docker-compose-microservices-gpu.yml`: legacy local GPU lab stack.
- `docker-compose-standalone.yml`, `docker-compose.yml`, `docker-compose-gpu*.yml`: legacy standalone/lab stacks.

They expose broader host ports, use demo credentials, and may use tmpfs preview storage. Do not treat them as the production HA contract.

## Quick Start

### Production Single-Server HA

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml up -d --build
```

Open:

- UI/API: `http://10.75.51.40:8000`
- Grafana: `http://10.75.15.3:4000`

### Production Multi-Server HA

On the control-plane host:

```bash
sudo docker compose --env-file .env.production.control-plane.local -f docker-compose.production.yml up -d --build
```

On the primary worker host:

```bash
sudo docker compose --env-file .env.production.primary.local -f docker-compose.production.yml up -d --build
```

On the backup worker host:

```bash
sudo docker compose --env-file .env.production.backup.local -f docker-compose.production.yml up -d --build
```

### Local Microservices Lab

```powershell
docker compose -f docker-compose-microservices.yml up -d --build
```

Open:

- UI/API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:4000`

### Legacy Local Active/Passive HA

```powershell
docker compose -f docker-compose-microservices-ha.yml up -d --build
```

Open:

- UI/API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:4000`

### Standalone

```powershell
docker compose -f docker-compose-standalone.yml up -d --build
```

Open:

- UI/API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## Service Configuration

Example active/passive SRT listener service:

```json
{
  "name": "Main Encoder Feed",
  "source_protocol": "srt",
  "source_mode": "listener",
  "source_ip": "0.0.0.0",
  "source_port": 9000,
  "destination_url": "udp://239.10.10.10:5000",
  "target_node": "primary",
  "ha_mode": "active_passive",
  "failover_node": "backup",
  "failover_after_seconds": 15,
  "failback_policy": "manual",
  "node_bindings": {
    "primary": {
      "input_bind_ip": "10.50.1.21",
      "output_bind_ip": "10.50.1.21"
    },
    "backup": {
      "input_bind_ip": "10.50.1.22",
      "output_bind_ip": "10.50.1.22"
    }
  },
  "enabled": true
}
```

### Core Fields

| Field | Description |
| --- | --- |
| `name` | Friendly service name. |
| `source_protocol` | `srt`, `udp`, `rtmp`, `rist`, or `hls`. |
| `source_mode` | `listener` or `caller`. Most relevant for SRT/RTMP/RIST. |
| `source_ip` | Source address. For listener mode, often `0.0.0.0`. |
| `source_port` | Input port, 1-65535. Required except for HLS sources. |
| `source_path` | RTMP path, for example `/live/stream`. |
| `source_url` | HLS source URL. Required when `source_protocol` is `hls`. |
| `destination_url` | Output URL. Must start with `rtmp://`, `rtmps://`, `srt://`, `udp://`, or `rist://`. May be empty when low-res or full HLS output is enabled. |
| `enabled` | Whether the service should run. |

### Route Editor V2 Structured Fields

The API also accepts additive structured route fields for the Route Editor V2 contract:

| Field | Description |
| --- | --- |
| `source` | Optional protocol-aware source object with endpoint, link parameter, SRT parameter, Stream ID, HLS URL, and path redundancy fields. When supplied, the API derives worker-compatible flat fields such as `source_protocol`, `source_ip`, `source_port`, `source_url`, `latency_ms`, `passphrase`, and custom `streamid`. |
| `destinations` | Optional list of protocol-aware normal destinations. This release supports one enabled normal destination and derives `destination_url` for current workers. Additional generated HLS outputs remain configured through `hls_outputs`, not `destinations`. |

The existing flat fields remain supported for compatibility. The browser UI now writes these structured fields while preserving flat worker-compatible fields. Broader FFmpeg structured runtime mapping remains a future backlog item.

The configured multicast policy range defines accepted source ports. Production host-network workers bind the selected host interface and service port directly, so there is no separate Docker-published worker port window.

The Route Editor V2 UI is protocol-aware:

- Source controls show only the selected protocol's relevant fields for SRT, UDP, RTMP, RIST, or HLS.
- Destination controls support SRT, UDP, RTMP, RTMPS, RIST, or raw URL compatibility.
- UDP source and destination controls include unicast/multicast type selection.
- SRT source and destination controls include listener/caller mode plus default/custom Stream ID state.
- SRT destination supports manual path redundancy as a secondary endpoint row in the structured config. Main Video defaults the secondary path to Backup Video, Backup Video defaults the secondary path to Main Video, and DMZ Video defaults the secondary path to DMZ Video until the operator overrides it. This stores the path model only; worker failover behavior is still controlled by `target_node`, `ha_mode`, `failover_node`, and Redis leases.
- `pbkeylen` remains a top-level legacy field. It is not serialized inside `source.srt` or `destinations[].srt`.

### Network Fields

| Field | Description |
| --- | --- |
| `local_bind_ip` | Default video-network IP for FFmpeg binding. |
| `node_bindings` | Per-node binding map. `input_bind_ip` controls source-side binding and `output_bind_ip` controls SRT/UDP destination binding where supported. Legacy `local_bind_ip` remains a fallback. |

### SRT/Advanced Fields

| Field | Description |
| --- | --- |
| `latency_ms` | SRT latency parameter. |
| `passphrase` | SRT encryption passphrase. |
| `pbkeylen` | SRT key length: `16`, `24`, or `32`. |
| `streamid` | SRT stream ID. |
| `backup_input_ip` | Alternate input address used for input-level failover. |
| `auto_failover` | Switches between main and backup input when FFmpeg fails. |
| `strict_probing` | Kills/restarts streams with severe probe or continuity errors. |
| `enable_hls_preview` | Compatibility flag for low-res HLS output. When true, low-res HLS is enabled. |
| `hls_outputs` | Optional HLS output profiles. `low_res` generates 360p/480p with a short buffer; `full_res` generates 720p/1080p with configurable buffer up to 24 hours. |

### HA Fields

| Field | Description |
| --- | --- |
| `ha_mode` | `manual`, `active_passive`, or `active_active`. Active/passive is implemented with leases. |
| `target_node` | Preferred active owner. |
| `failover_node` | Passive owner for active/passive mode. |
| `failover_after_seconds` | Lease/heartbeat timeout window. Valid range: 5-300 seconds. |
| `failback_policy` | `manual` or `automatic`. Manual is recommended and currently the safe default. |

## API Examples

Create a disabled service:

```powershell
$body = @{
  name = "Test SRT"
  source_protocol = "srt"
  source_mode = "caller"
  source_ip = "127.0.0.1"
  source_port = 9900
  destination_url = "udp://239.10.10.10:5000"
  target_node = "primary"
  enabled = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/services -ContentType "application/json" -Body $body
```

List services:

```powershell
Invoke-RestMethod http://localhost:8000/api/services
```

Start a service:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/services/<service_id>/start
```

Stop a service:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/services/<service_id>/stop
```

Delete a service:

```powershell
Invoke-RestMethod -Method Delete http://localhost:8000/api/services/<service_id>
```

## Preview Output

Workers write previews into:

```text
frontend/previews/<service_id>/
```

Thumbnail:

```text
/previews/<service_id>/preview.jpg
```

Optional HLS playlist:

```text
/previews/<service_id>/low_res/stream.m3u8
/previews/<service_id>/full_res/stream.m3u8
```

In single-server production deployments, the API and workers share this path through the `shared_previews` Docker volume. In multi-server deployments, set `PREVIEW_STORAGE` to a real shared filesystem path mounted on every control-plane and worker host. Without shared storage, the UI cannot serve worker-generated preview images or HLS playlists from another physical server.

Low-res HLS writes 360p and 480p renditions. Full HLS writes 720p and 1080p renditions and can keep up to 24 hours of local buffer.

## Metrics

Prometheus scrapes telemetry from:

```text
telemetry:9090/metrics
```

Main metrics include:

- system CPU by node
- system memory by node
- active service count
- error service count
- stream bitrate
- continuity counter/errors

Prometheus UI:

```text
http://localhost:9090
```

Grafana:

```text
http://localhost:4000
```

Default Grafana password in compose is currently:

```text
admin
```

Change it before production use.

## Testing

Install test dependencies locally if needed:

```powershell
pip install -r requirements.txt -r requirements-test.txt
```

Run tests:

```powershell
python -m pytest -q
```

Run tests inside the API container:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pip install -r requirements-test.txt
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest -q
```

## Operational Notes

- Redis Pub/Sub is used for immediate commands.
- Redis hashes are used for desired service config and live worker metrics.
- Workers reconcile from Redis desired config so they can recover from missed Pub/Sub commands.
- Active/passive ownership uses Redis leases.
- Workers heartbeat into Redis.
- A worker stops its local FFmpeg process if it loses its lease.
- Existing Postgres databases get missing HA columns added during API startup.
- Full HLS capacity is limited by `MAX_FULL_HLS_SERVICES`. Disabled Full HLS templates do not count until they are started or otherwise enabled.
- HLS startup checks `HLS_MIN_FREE_BYTES` and optionally rejects oversized estimated buffers with `HLS_STORAGE_QUOTA_BYTES`.

## Production Caveats

- Default compose passwords are demo values. Change Postgres and Grafana credentials.
- Lab compose exposes Redis on host port `6379`. Production Redis requires authentication and binds to loopback for single-server or Management only for multi-server HA.
- For multi-server HA, Redis/Postgres must themselves be reliable and reachable on the management network.
- Host-network workers share the host namespace. The API rejects enabled services that would claim the same input bind IP and UDP port.
- Invalid bind interfaces, out-of-policy ports, occupied ports, and multicast join failures are stable non-retryable errors until configuration changes or the operator explicitly retries.
- Production HLS output should use disk-backed `shared_previews` storage sized for the expected buffer duration. A small tmpfs preview volume is suitable only for thumbnails or lab use.
- Automatic failback should be treated carefully. Manual failback avoids stream flapping.

## Useful Docker Commands

Show running services:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml ps
```

Follow API logs:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml logs -f api
```

Follow worker logs:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml logs -f worker-primary
```

Stop the stack:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml down
```

Rebuild:

```bash
sudo docker compose --env-file .env.production.single-server.local -f docker-compose.production.yml up -d --build
```

# SRT Gateway

SRT Gateway is a web-managed stream routing gateway for SRT, UDP, RTMP, and RIST sources. It runs FFmpeg pipelines from service definitions, exposes a browser UI/API, publishes metrics, and supports worker-node redundancy for broadcast-style deployments.

## What It Does

- Creates and manages stream routing services from a web UI or REST API.
- Supports SRT, UDP, RTMP, and RIST inputs.
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

### Microservices Mode

The API, workers, telemetry, Redis, Postgres, Prometheus, and Grafana run as separate services.

Use this for:

- production-style deployments
- active/passive worker redundancy
- two physical servers
- one physical server with two redundant workers

Compose files:

- `docker-compose-microservices.yml`
- `docker-compose-microservices-gpu.yml`
- `docker-compose-microservices-ha.yml`
- `docker-compose.production.yml` for explicit production layouts with management-bound API/Grafana and primary/backup worker profiles

Recommended production direction: **microservices mode**.

## Network Model

Recommended facility layout:

- **Management network:** API/UI, Redis, Postgres, worker heartbeats, leases, telemetry.
- **Video network:** SRT/UDP/RIST/RTMP media ingress and egress.

Keep control traffic and media traffic separated where possible.

### Management Network

These values should use management-network DNS/IPs:

- `DATABASE_URL`
- `REDIS_URL`
- API/UI access
- Prometheus/Grafana access
- worker heartbeat and lease traffic

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

## Redundancy Model

The active/passive implementation is based on Redis heartbeats and per-service leases.

Each worker has a `NODE_ROLE`, such as:

- `primary`
- `backup`
- `worker_1`
- `worker_2`

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

### Option 1: Two Physical Servers

Recommended for facility redundancy.

Server A:

- worker with `NODE_ROLE=primary`
- optional API/UI

Server B:

- worker with `NODE_ROLE=backup`
- optional API/UI

Shared or reachable from both:

- Postgres
- Redis
- telemetry stack if desired

Example worker environment:

```yaml
environment:
  - REDIS_URL=redis://<management-redis-ip>:6379/0
  - NODE_ROLE=primary
  - PYTHONUNBUFFERED=1
```

For the backup server:

```yaml
environment:
  - REDIS_URL=redis://<management-redis-ip>:6379/0
  - NODE_ROLE=backup
  - PYTHONUNBUFFERED=1
```

Use `node_bindings` so each physical server binds to its own video-network IP.

### Option 2: One Physical Server With Two Redundant Workers

Use `docker-compose-microservices-ha.yml`.

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

```powershell
docker compose -f docker-compose-microservices-ha.yml up -d --build
```

Important: two containers cannot publish the same UDP host ports on the same host IP. The HA compose maps backup ports as:

```text
worker-primary: 9000-9010 -> 9000-9010/udp
worker-backup:  9011-9021 -> 9000-9010/udp
```

If the server has multiple video NIC IPs, you can instead bind both workers to the same UDP port range on different host IPs:

```yaml
worker-primary:
  ports:
    - "10.50.1.21:9000-9010:9000-9010/udp"

worker-backup:
  ports:
    - "10.50.1.22:9000-9010:9000-9010/udp"
```

## Quick Start

### Microservices

```powershell
docker compose -f docker-compose-microservices.yml up -d --build
```

Open:

- UI/API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:4000`

### Local Active/Passive HA

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
  target_node = "worker_1"
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
/previews/<service_id>/stream.m3u8
```

In microservice deployments, the API and workers share this path through the `shared_previews` Docker volume.

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

## Production Caveats

- Default compose passwords are demo values. Change Postgres and Grafana credentials.
- Redis is currently exposed on host port `6379` in compose. Restrict this on real networks.
- For true two-server HA, Redis/Postgres must themselves be reliable and reachable on the management network.
- For one-server two-worker HA, duplicate UDP host ports require either separate video IPs/NICs or shifted host port mappings.
- Automatic failback should be treated carefully. Manual failback avoids stream flapping.
- The UI currently preserves `node_bindings`, but a dedicated editor for per-node video NIC assignment is still a recommended future improvement.

## Useful Docker Commands

Show running services:

```powershell
docker compose -f docker-compose-microservices.yml ps
```

Follow API logs:

```powershell
docker compose -f docker-compose-microservices.yml logs -f api
```

Follow worker logs:

```powershell
docker compose -f docker-compose-microservices.yml logs -f worker
```

Stop the stack:

```powershell
docker compose -f docker-compose-microservices.yml down
```

Rebuild:

```powershell
docker compose -f docker-compose-microservices.yml up -d --build
```

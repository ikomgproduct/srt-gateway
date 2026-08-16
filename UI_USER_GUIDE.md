# SRT Gateway UI User Guide

This guide explains how to operate the SRT Gateway web interface after the system is installed and running.

For your physical server layout:

- UI/API: `http://10.75.51.40:8000`
- Primary video worker: `primary`, bound to Video Main `10.70.15.3`
- Backup video worker: `backup`, bound to Video Backup `10.71.15.3`
- Monitoring: Grafana `http://10.75.15.3:4000`, Prometheus `http://10.75.15.3:9090`

## Opening The UI

Open the browser to:

```text
http://10.75.51.40:8000
```

The main screen is the Dashboard. It lists all configured routing services and shows their current state, source, destination, active input, worker target, encryption state, preview, and action buttons.

## Dashboard Columns

### Status / Name

Shows the service name and runtime status.

Common statuses:

| Status | Meaning |
| --- | --- |
| `stopped` | Service is configured but not running. |
| `starting` | Worker received the start command and is preparing FFmpeg. |
| `running` | FFmpeg is running for this service. |
| `error` | FFmpeg or service startup failed. Hover the error tag for full details. |
| `pending worker` | The service is enabled, but no online worker matches its target node. |

If an error exists, an `Error` or `No eligible worker` tag is shown under the status. Move the mouse over the tag to see the full message.

### Protocol / Mode

Shows the source protocol and source mode.

Supported source protocols:

- `SRT`
- `RTMP`
- `UDP`
- `RIST`
- `HLS`

For HLS sources, the network source fields are hidden and the form shows `HLS Source URL`.

Common modes:

- `listener`: the gateway waits for an incoming connection.
- `caller`: the gateway connects to a remote source.

### Source

Shows the computed full source URL. Use the copy button to copy it.

For example:

```text
srt://0.0.0.0:9000?mode=listener
rtmp://54.235.122.142:1935/Jungotv/AWSN03
```

If a backup input is configured, the table shows both `Main` and `Backup` source rows.

### Destination

Shows the full destination URL. Use the copy button to copy it.

Examples:

```text
udp://239.10.10.10:5000
srt://10.70.20.50:9000?mode=caller&streamid=feed1
rtmp://example.com/live/stream-key
```

### Input

Shows which input is active:

- `MAIN FEED`
- `BACKUP FEED`

It also shows the target worker node:

- `PRIMARY NODE`
- `BACKUP NODE`
- `ALL NODE`

For your physical single-server redundant setup, use:

- `primary` for Video Main
- `backup` for Video Backup

### Encryption

Shows whether SRT encryption is configured.

Possible values:

- `None`
- `128-bit`
- `192-bit`
- `256-bit`

### Live Preview

When a service is running, the UI shows a still preview image if FFmpeg can generate one.

If HLS output is enabled for the service, the UI shows separate `Low HLS` and/or `Full HLS` link buttons depending on the selected output profile.

### Actions

Available buttons:

| Button | Meaning |
| --- | --- |
| Start | Starts the service. |
| Stop | Stops the service. |
| Feed | Manually switches between main and backup input. |
| Move | Cycles the target node between `primary`, `backup`, and `all`. |
| Gear | Opens edit mode. |
| Trash | Deletes the service after confirmation. |

## Creating A New Service

Click `New Service`.

### Basic Fields

#### Service Name

Enter a clear name, for example:

```text
Studio A Main Encoder
```

#### Source Protocol

Select the input protocol:

- `SRT`
- `RTMP`
- `UDP`
- `RIST`
- `HLS`

#### Source Mode

Choose:

- `Listener`: gateway listens for the source.
- `Caller`: gateway connects to the source.

For SRT listener input, common values are:

```text
Source Protocol: SRT
Source Mode: Listener
Main Source IP: 0.0.0.0
Source Port: 9000
```

#### Main Source IP

For listener mode, usually use:

```text
0.0.0.0
```

For caller mode, enter the remote source IP or hostname.

#### Source Port

Enter the input port.

For your compose layout, both workers expose:

```text
9000-9010/udp
```

#### HLS Source URL

For HLS sources, enter the playlist URL:

```text
https://example.com/live/stream.m3u8
```

#### Backup Source IP

Optional. Use this for input-level source failover, not worker failover.

Example:

```text
Main Source IP: 10.70.20.10
Backup Source IP: 10.71.20.10
```

#### Auto Feed Failover

When enabled, the worker can switch between main and backup input after FFmpeg/input failure.

This is different from active/passive worker failover.

#### Strict Health Probing

Enables more aggressive detection of stream problems such as missing video or continuity errors.

Use carefully. It can restart bad feeds faster, but unstable sources may flap more often.

#### Enable Low-Res HLS Output

Creates lightweight local HLS outputs for the service.

Use this when an external preview player needs access to low-resolution streams.

Low-res HLS generates 360p and 480p renditions with a short rolling buffer.

#### Enable Full HLS Output

Creates local 720p and 1080p HLS outputs for the service.

Full HLS can use significant CPU/GPU and disk capacity. The buffer duration is configurable up to 24 hours.

When low-res or full HLS output is enabled, the normal destination URL can be left empty.

## RTMP Source Path

For RTMP sources, use `Source Path`.

Example source:

```text
Host: 54.235.122.142
Port: 1935
App/Path: /Jungotv
Stream Key: AWSN03
```

Enter:

```text
Main Source IP: 54.235.122.142
Source Port: 1935
Source Path: /Jungotv/AWSN03
```

The UI will display:

```text
rtmp://54.235.122.142:1935/Jungotv/AWSN03
```

## Destination Configuration

You can either type a raw destination URL or use the Destination Builder.

### Raw Destination URL

Select:

```text
Destination Builder: Use URL field directly
```

Then enter the destination URL manually.

Supported destination prefixes:

- `rtmp://`
- `rtmps://`
- `srt://`
- `udp://`
- `rist://`

### RTMP Destination Builder

Select:

```text
Destination Builder: RTMP destination
```

Fill:

- Destination Host/IP
- Destination Port
- RTMP App/Path
- RTMP Stream Key

Example:

```text
Destination Host/IP: live.example.com
Destination Port: 1935
RTMP App/Path: /live
RTMP Stream Key: abc123
```

The UI assembles:

```text
rtmp://live.example.com:1935/live/abc123
```

### SRT Destination Builder

Select:

```text
Destination Builder: SRT destination
```

Fill:

- Destination Host/IP
- Destination Port
- SRT Mode
- SRT Stream ID, optional
- SRT Passphrase, optional
- SRT Key Size, optional

Example:

```text
Destination Host/IP: 10.70.20.50
Destination Port: 9000
SRT Mode: Caller
SRT Stream ID: feed1
```

The UI assembles:

```text
srt://10.70.20.50:9000?mode=caller&streamid=feed1
```

### UDP Destination Builder

Select:

```text
Destination Builder: UDP destination
```

Fill:

- Destination Host/IP
- Destination Port
- UDP TTL, optional
- UDP Packet Size, optional

Example:

```text
Destination Host/IP: 239.10.10.10
Destination Port: 5000
UDP TTL: 16
```

The UI assembles:

```text
udp://239.10.10.10:5000?ttl=16
```

## Worker Target Selection

The `Hardware Exec Node` field controls which worker should run the service.

Options:

| Option | Use Case |
| --- | --- |
| `primary` | Run only on the primary worker. |
| `backup` | Run only on the backup worker. |
| `all` | Run on all eligible workers. |

For your physical single-server two-worker setup:

- Choose `primary` to run on Video Main `10.70.15.3`.
- Choose `backup` to run on Video Backup `10.71.15.3`.

If a service shows `pending worker`, check that its target matches an online worker.

Example:

```text
No eligible worker online. Service targets: primary. Online workers: worker_1.
```

This means the service targets `primary`, but only `worker_1` is currently online.

## Advanced Settings

Click `Toggle Advanced Settings (Encryption, NIC Bindings)`.

### Interface Bindings

The UI exposes primary and backup input/output interface dropdowns populated from the configured hardware inventory.

Fields:

- Primary Input Interface
- Primary Output Interface
- Backup Input Interface
- Backup Output Interface

For listener-mode SRT, the input interface can bind the listening socket to a specific video NIC. For caller-mode SRT and UDP inputs, it is sent as `localaddr` where supported. For SRT/UDP destinations, the output interface is sent as destination `localaddr` where supported.

For your server:

```text
Primary worker video IP: 10.70.15.3
Backup worker video IP: 10.71.15.3
```

### SRT Latency

Sets SRT latency in milliseconds.

Common starting values:

```text
120
250
500
```

### SRT Passphrase

Sets the SRT encryption passphrase.

Only use when the sender/receiver is configured with the same passphrase.

### SRT Key Size

Choose:

- None
- 16 Bytes, 128-bit
- 24 Bytes, 192-bit
- 32 Bytes, 256-bit

### SRT Stream ID

Optional SRT routing identifier.

Use this when the remote SRT system requires stream IDs for routing or authentication.

## Editing A Service

Click the gear button.

The same form opens with the existing service values.

Make the needed changes, then click `Save Service`.

When a running service is saved, the workers receive an updated config and restart/reconcile the FFmpeg process.

## Starting And Stopping

To start a service:

1. Click `Start`.
2. Watch the status change to `starting`.
3. If successful, it changes to `running`.
4. If it fails, it changes to `error`.

To stop a service:

1. Click `Stop`.
2. The status changes to `stopped`.

## Manual Feed Switch

When a service is running and has a backup input, use `Feed` to manually switch between main and backup input.

The `Input` column shows the active feed.

## Moving Between Workers

The `Move` button cycles the service target:

```text
primary -> backup -> all -> primary
```

Use this for manual testing or manual failover.

For planned operation, edit the service and set the desired target directly.

## Deleting A Service

Click the trash button.

The UI asks for confirmation before deleting.

Deleting a service removes the configuration and sends a stop command to workers.

## Recommended Service Patterns

### SRT Listener On Primary Video Network

```text
Source Protocol: SRT
Source Mode: Listener
Main Source IP: 0.0.0.0
Source Port: 9000
Destination URL: udp://239.10.10.10:5000
Hardware Exec Node: primary
```

The source listens on:

```text
10.70.15.3:9000/udp
```

because the primary worker ports are bound to `10.70.15.3`.

### SRT Listener On Backup Video Network

```text
Source Protocol: SRT
Source Mode: Listener
Main Source IP: 0.0.0.0
Source Port: 9000
Destination URL: udp://239.10.10.10:5000
Hardware Exec Node: backup
```

The source listens on:

```text
10.71.15.3:9000/udp
```

because the backup worker ports are bound to `10.71.15.3`.

### RTMP Caller Source

For:

```text
rtmp://54.235.122.142:1935/Jungotv/AWSN03
```

Use:

```text
Source Protocol: RTMP
Source Mode: Caller
Main Source IP: 54.235.122.142
Source Port: 1935
Source Path: /Jungotv/AWSN03
```

## Troubleshooting

### Service Shows Pending Worker

Cause:

The service target does not match any online worker heartbeat.

Check:

- Is `worker-primary` running?
- Is `worker-backup` running?
- Does the service target match `primary`, `backup`, or `all`?

Command:

```bash
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml ps
```

### Service Shows Error

Hover the error tag in the UI.

Common causes:

- FFmpeg could not connect to the source.
- Invalid source URL or destination URL.
- Wrong SRT mode.
- Port is already in use.
- Missing network route to source/destination.
- SRT encryption mismatch.

Check worker logs:

```bash
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml logs -f worker-primary
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml logs -f worker-backup
```

### No Preview

Possible causes:

- Service is not running.
- Source has no video track.
- FFmpeg has not generated the first preview frame yet.
- The stream is audio-only.

### Start Button Does Nothing

The UI now shows explicit start errors. If no alert appears, check the status:

- `starting`: worker is preparing FFmpeg.
- `running`: service started.
- `pending worker`: target does not match any online worker.
- `error`: hover the error tag.

### Source Cannot Connect To Listener

Check that the sender is using the correct video IP:

```text
Primary: 10.70.15.3
Backup:  10.71.15.3
```

Also verify the selected port is within the exposed range:

```text
9000-9010/udp
```

### UI Not Reachable

For your physical server, use:

```text
http://10.75.51.40:8000
```

Check:

```bash
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml ps
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml logs -f api
```

## Daily Operations Checklist

1. Open the UI.
2. Confirm services show `running`.
3. Confirm each service target is correct: `primary`, `backup`, or `all`.
4. Hover any error tags and record the full message.
5. Check Grafana if stream or server metrics look abnormal.
6. Before deleting services, confirm the stream is no longer needed.

## Build And Restart Commands

After updating the server repository:

```bash
git pull --ff-only origin main
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml build
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml up -d
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml ps
```

If the Dockerfile was changed and you want a fully fresh build:

```bash
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml build --no-cache
sudo docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml up -d
```

# Network Zone Architect Handoff

## Goal

Define the technical direction for SRT Gateway network-zone routing so Dev Lead can prepare a scoped implementation plan.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Product Decisions Reviewed

Product Lead confirmed the target site network model:

- Main Video: `eno1`, `10.70.15.3`, internal video input/output.
- Backup Video: `eno2`, `10.71.15.3`, internal video input/output.
- DMZ Video: `eno3`, `10.75.51.40`, public/external video input/output.
- Management: `eno4`, `10.75.15.3`, API, SSH, Grafana/admin, and internal control-plane communication.

Confirmed behavior:

- DMZ Video must be selectable for input and output on primary and backup workers.
- Main Video and Backup Video are paired internal redundant paths.
- If Main Video is selected as the primary internal path, Backup Video should be selected for the paired path.
- If Backup Video is selected as the primary internal path, Main Video should be selected for the paired path.
- Management must not appear as a media route input/output option.
- UI/Grafana user access still comes through DMZ.
- Internal API/service communication should use Management.
- UI labels should group route interfaces as Main Video, Backup Video, and DMZ Video for now.
- Worker UDP bind IPs and port ranges must remain configurable through env files.

## Current Shape

The current implementation has the right first building blocks but is still worker-role centric:

- `/api/interfaces` in `api/main.py` returns `INTERFACE_INVENTORY_JSON` or `DEFAULT_INTERFACE_INVENTORY`.
- Current inventory entries support `id`, `label`, `ip`, `node_roles`, `directions`, and `network`.
- `frontend/app.js` filters interface dropdowns by `node_roles` and `directions`.
- Route source and primary destination dropdowns are hard-wired to primary role.
- Destination secondary path is hard-wired to backup role.
- `docker-compose.production.yml` exposes one UDP host IP range per worker:
  - `PRIMARY_VIDEO_IP:PRIMARY_PORT_RANGE`
  - `BACKUP_VIDEO_IP:BACKUP_PORT_RANGE`
- Env examples define two video interfaces, not the full Main/Backup/DMZ/Management zone model.

## Proposed Architecture

Separate three concepts:

- Worker role: `primary`, `backup`, `all`.
- Network zone: `main-video`, `backup-video`, `dmz-video`, `management`.
- Route direction: `input`, `output`.

Route source/destination interface dropdowns should filter on:

- `purpose == "video"` or legacy `network == "video"`.
- `directions` includes `input` or `output`.
- `zone != "management"`.

Worker binding controls may still use `node_roles`, but route endpoint selection should become zone-aware rather than role-only.

The route editor should store selected endpoint details in the existing structured contract:

```json
{
  "interface_id": "dmz-video",
  "bind_ip": "10.75.51.40",
  "address": "0.0.0.0",
  "port": 9000
}
```

Do not add a new persistence table in this slice. Continue using the current structured `source` and `destinations` JSON contract.

## Interface Inventory Schema

Extend the existing inventory entries additively:

```json
{
  "id": "dmz-video",
  "label": "DMZ Video",
  "ip": "10.75.51.40",
  "nic": "eno3",
  "zone": "dmz-video",
  "purpose": "video",
  "node_roles": ["primary", "backup"],
  "directions": ["input", "output"]
}
```

Required compatibility behavior:

- Existing entries without `zone` must continue working.
- Existing entries without `purpose` should be treated as video when `network == "video"`.
- Existing `network` should remain accepted as a legacy alias.
- Entries with `purpose == "management"` or `zone == "management"` must not appear in media route endpoint dropdowns.
- Unknown selected legacy bind IPs must still be preserved as `Existing interface (<ip>)` during edit.

Recommended built-in defaults:

```json
[
  {
    "id": "main-video",
    "label": "Main Video",
    "ip": "10.70.15.3",
    "nic": "eno1",
    "zone": "main-video",
    "purpose": "video",
    "node_roles": ["primary", "backup"],
    "directions": ["input", "output"]
  },
  {
    "id": "backup-video",
    "label": "Backup Video",
    "ip": "10.71.15.3",
    "nic": "eno2",
    "zone": "backup-video",
    "purpose": "video",
    "node_roles": ["primary", "backup"],
    "directions": ["input", "output"]
  },
  {
    "id": "dmz-video",
    "label": "DMZ Video",
    "ip": "10.75.51.40",
    "nic": "eno3",
    "zone": "dmz-video",
    "purpose": "video",
    "node_roles": ["primary", "backup"],
    "directions": ["input", "output"]
  },
  {
    "id": "management",
    "label": "Management",
    "ip": "10.75.15.3",
    "nic": "eno4",
    "zone": "management",
    "purpose": "management",
    "node_roles": [],
    "directions": []
  }
]
```

## UI Behavior

Route endpoint dropdowns:

- Source Input Interface: show video interfaces that allow `input`.
- Destination Output Interface: show video interfaces that allow `output`.
- Secondary/paired path interface: show video interfaces that allow `output`, excluding Management.
- Group labels by `zone` for readability: Main Video, Backup Video, DMZ Video.

Internal pairing:

- When the selected primary route endpoint is Main Video, default the paired secondary endpoint to Backup Video.
- When the selected primary route endpoint is Backup Video, default the paired secondary endpoint to Main Video.
- When the selected primary route endpoint is DMZ Video, default the paired endpoint to DMZ Video unless Product later defines a better rule.
- Preserve manual operator overrides after the user changes the secondary endpoint.

Scope note:

- Pairing should be a UI defaulting/helper behavior for route configuration. It must not be confused with Redis worker lease ownership or `target_node`.

## Production Compose Strategy

Keep `docker-compose.production.yml` as the canonical production file.

Bridge networking with explicit port publishing remains the recommended path for now. Avoid host networking unless implementation proves Docker port publishing cannot support the needed shape.

Production compose should support publishing worker UDP ranges on multiple video IPs through env-configurable variables.

Recommended single-server defaults:

- Primary worker:
  - Main Video `10.70.15.3`, port range `9000-9010`.
  - DMZ Video `10.75.51.40`, port range `9000-9010`.
- Backup worker:
  - Backup Video `10.71.15.3`, port range `9011-9021`.
  - DMZ Video `10.75.51.40`, port range `9011-9021`.

Suggested env direction:

```env
PRIMARY_VIDEO_BINDINGS=10.70.15.3:9000-9010:9000-9010/udp,10.75.51.40:9000-9010:9000-9010/udp
BACKUP_VIDEO_BINDINGS=10.71.15.3:9011-9021:9000-9010/udp,10.75.51.40:9011-9021:9000-9010/udp
```

Dev Lead should validate whether Compose can express env-expanded multiple port mappings safely. If not, use explicit optional variables such as:

```env
PRIMARY_MAIN_VIDEO_IP=10.70.15.3
PRIMARY_DMZ_VIDEO_IP=10.75.51.40
PRIMARY_PORT_RANGE=9000-9010
BACKUP_BACKUP_VIDEO_IP=10.71.15.3
BACKUP_DMZ_VIDEO_IP=10.75.51.40
BACKUP_HOST_PORT_RANGE=9011-9021
BACKUP_CONTAINER_PORT_RANGE=9000-9010
```

Compose implementation must preserve lab compatibility where a site only has one video IP or uses the same IP for both worker roles, with split port ranges to avoid conflicts.

## UI/Grafana Exposure Decision

Architect recommendation for this slice:

- Keep direct bind support because it matches the current deployment and is simple to operate.
- Document the safer future option: DMZ reverse proxy to management-bound API/Grafana.
- Do not expose Redis/Postgres to DMZ.
- Do not bind API/Grafana to `0.0.0.0` in production examples.

This means current production env examples may keep DMZ-facing UI/Grafana bind variables, but docs must be clear that Redis/Postgres remain internal or management-only.

## Files Likely Affected

- `api/main.py`
  - Extend default interface inventory.
  - Optionally normalize inventory entries for compatibility before returning `/api/interfaces`.
- `frontend/app.js`
  - Add zone-aware filtering.
  - Add grouped option labels or `optgroup`s.
  - Add Main/Backup pairing default behavior.
  - Preserve legacy selected IP behavior.
- `frontend/index.html`
  - Only if labels or helper structure need markup changes.
- `frontend/style.css`
  - Only if grouped dropdown/help layout needs styling.
- `docker-compose.production.yml`
  - Publish worker UDP ports for multiple video IPs.
- `.env.production.single-server.example`
- `.env.production.control-plane.example`
- `.env.production.primary.example`
- `.env.production.backup.example`
- `README.md`
- `UI_USER_GUIDE.md`
- `.agent-context.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `backlog/tasks.md`
- `tests/test_api_validation.py`
- `tests/test_frontend_static.py`

## Compatibility Requirements

- Existing `INTERFACE_INVENTORY_JSON` values must continue to work.
- Existing saved services with `interface_id`, `bind_ip`, `node_bindings`, `local_bind_ip`, `backup_input_ip`, and `worker_1` must continue to hydrate and save.
- Existing Route Editor V2 `source` and `destinations` payloads must remain valid.
- Do not remove legacy flat compatibility fields.
- Do not require all four NICs in lab mode.

## Verification Plan

Dev Lead should require implementation tests for:

1. `/api/interfaces` returns zone-aware defaults with Main Video, Backup Video, DMZ Video, and Management.
2. `/api/interfaces` preserves legacy env inventory entries without `zone` or `purpose`.
3. Frontend static tests prove route source/destination dropdowns filter by video purpose/direction and exclude Management.
4. Frontend static tests prove current legacy `node_roles` filtering remains available for worker binding controls.
5. Frontend static tests prove Main Video defaults secondary path to Backup Video, and Backup Video defaults secondary path to Main Video.
6. Compose config renders for single-server env.
7. Compose config renders for control-plane, primary-worker, and backup-worker env examples.
8. Full regression still passes in the API container.

Recommended manual QA:

1. Create SRT listener input on DMZ Video and output to Main Video.
2. Create internal Main Video input and DMZ Video output.
3. Enable path redundancy and confirm Main defaults paired path to Backup.
4. Enable path redundancy and confirm Backup defaults paired path to Main.
5. Confirm Management never appears as a route endpoint.
6. Confirm worker UDP ports bind only to configured video IPs and port ranges.

## Risks

- Docker Compose may not support a clean comma-delimited multi-port env expansion; Dev Lead should validate before implementation.
- Binding the same UDP container port range to multiple host IPs must be tested on the target Docker version.
- Same-IP lab deployments still need split host port ranges to avoid conflicts.
- Direct DMZ binding for UI/Grafana is operationally convenient but weaker than a reverse proxy pattern.
- UI pairing defaults must not overwrite operator overrides during edit.
- Management IP must not leak into media dropdowns.

## Questions For Dev Lead

No blocking product questions remain.

Technical validation questions for Dev Lead:

- Can the current Docker Compose version safely expand multiple port mappings from one env variable, or should we use explicit optional mapping variables?
- Should interface normalization happen only in the frontend, or should `/api/interfaces` return normalized `zone` and `purpose` fields for every entry?
- Should pairing defaults be implemented only when path redundancy is enabled, or also for primary/backup worker binding defaults?

Architect recommendation:

- Normalize inventory in the API and keep frontend filtering simple.
- Apply pairing defaults only to route path redundancy first; leave worker binding defaults unchanged unless Product asks for that behavior.

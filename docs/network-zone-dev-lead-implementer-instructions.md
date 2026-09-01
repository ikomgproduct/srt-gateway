# Network Zone Dev Lead Implementer Instructions

## Goal

Implement backlog item 12: zone-aware interface inventory, route endpoint filtering/defaulting, and production compose/env updates for the SRT Gateway site network model.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Source Material

Read before implementation:

- `.agent-context.md`
- `backlog/tasks.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `docs/network-zone-product-handoff.md`
- `docs/network-zone-architect-handoff.md`

## Implementation Verdict

No additional Architect review is needed before implementation. Product decisions are resolved, and the remaining questions are Dev Lead implementation constraints:

- Do not use a comma-delimited env variable to generate multiple Compose `ports:` list entries.
- Normalize interface inventory in the API.
- Apply Main/Backup pairing defaults only to route path redundancy in this slice.

## Required Changes

### 1. API Interface Inventory Normalization

File: `api/main.py`

Implement an additive normalization path for `/api/interfaces`.

Requirements:

- Update `DEFAULT_INTERFACE_INVENTORY` to include:
  - Main Video: `eno1`, `10.70.15.3`, `zone=main-video`, `purpose=video`.
  - Backup Video: `eno2`, `10.71.15.3`, `zone=backup-video`, `purpose=video`.
  - DMZ Video: `eno3`, `10.75.51.40`, `zone=dmz-video`, `purpose=video`.
  - Management: `eno4`, `10.75.15.3`, `zone=management`, `purpose=management`.
- Keep `network` present for compatibility.
- Add a helper such as `normalize_interface_inventory_item(item)` so env-provided legacy entries are enriched before returning.
- For legacy entries:
  - If `purpose` is missing and `network == "video"`, return `purpose: "video"`.
  - If `zone` is missing, derive it from `network` or `id` where practical; otherwise use the legacy `network` value.
  - Ensure `node_roles` and `directions` are always arrays.
  - Preserve unknown fields rather than dropping them.
- If `INTERFACE_INVENTORY_JSON` is invalid, preserve current fallback behavior to defaults.

Do not add a database table for interface inventory in this slice.

### 2. Frontend Zone-Aware Route Endpoint Filtering

File: `frontend/app.js`

Keep worker binding dropdowns role-aware, but change route source/destination endpoint dropdowns to be video-zone aware.

Requirements:

- Preserve the existing role-aware helper for worker binding controls:
  - `primaryInputBindIp`
  - `primaryOutputBindIp`
  - `backupNodeInputBindIp`
  - `backupNodeOutputBindIp`
- Add route endpoint filtering that includes entries where:
  - `purpose === "video"` or legacy `network === "video"`
  - `directions` contains the requested direction
  - `zone !== "management"` and `purpose !== "management"`
- Source Input Interface should show all video input zones.
- Destination Output Interface should show all video output zones.
- Destination Secondary Interface should show all video output zones.
- Preserve selected legacy IPs with `Existing interface (<ip>)` if no inventory entry matches.
- Group or label options by zone for now. Native `optgroup` is acceptable and preferred if it stays simple.

### 3. Main/Backup Pairing Defaults

File: `frontend/app.js`

Implement pairing as a route path-redundancy helper only.

Requirements:

- When path redundancy is enabled and the operator has not manually changed the secondary interface:
  - Main Video primary destination defaults secondary interface to Backup Video.
  - Backup Video primary destination defaults secondary interface to Main Video.
  - DMZ Video primary destination defaults secondary interface to DMZ Video.
- Manual secondary interface changes must be preserved.
- Edit hydration must preserve existing saved secondary endpoints and must not overwrite them.
- Do not change worker target selection semantics.
- Do not change Redis lease ownership behavior.
- Do not change primary/backup worker binding defaults in this slice.

### 4. Production Compose And Env Examples

Files:

- `docker-compose.production.yml`
- `.env.production.single-server.example`
- `.env.production.control-plane.example`
- `.env.production.primary.example`
- `.env.production.backup.example`

Requirements:

- Keep `docker-compose.production.yml` as the canonical production file.
- Do not use comma-delimited env variables as a substitute for YAML port list items.
- Use explicit optional env-backed port mappings or a clear compose-supported strategy.
- Keep port ranges env-configurable.
- Single-server production must support:
  - worker-primary on Main Video and DMZ Video.
  - worker-backup on Backup Video and DMZ Video.
  - split host port ranges when two workers share an IP, especially DMZ.
- Multi-server worker env examples must support each worker publishing on its local internal video IP plus DMZ video IP where available.
- Lab compatibility must remain possible with fewer NICs or shared IPs.
- API/Grafana direct DMZ bind variables may remain for current operations, but docs must make clear that Redis/Postgres are never exposed to DMZ.
- Do not bind production API/Grafana examples to `0.0.0.0`.

Dev Lead recommendation:

- Prefer explicit optional mappings over clever env parsing.
- If optional mappings cannot be cleanly disabled in Compose without invalid empty port entries, use a small documented override-file strategy for extra DMZ/video bindings.

### 5. Documentation Updates

Files:

- `README.md`
- `UI_USER_GUIDE.md`
- `.agent-context.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `backlog/tasks.md`

Requirements:

- Document the four-zone network model.
- Explain `INTERFACE_INVENTORY_JSON` versus Docker UDP publish bindings.
- Explain that Management must not be selected as a video route endpoint.
- Explain that DMZ Video is valid for source and destination.
- Explain Main/Backup pairing behavior for path redundancy.
- Explain that UI/Grafana may be DMZ-accessible, but Redis/Postgres stay internal or management-only.
- Update backlog item 12 implementation notes and verification status after implementation.

## Tests Required

Add or update automated tests.

Required test areas:

- `tests/test_api_validation.py`
  - `/api/interfaces` returns normalized defaults for Main Video, Backup Video, DMZ Video, and Management.
  - Env-provided legacy inventory without `zone` or `purpose` is normalized.
  - Invalid `INTERFACE_INVENTORY_JSON` falls back to defaults.
- `tests/test_frontend_static.py`
  - Route endpoint dropdown logic filters by video purpose/direction and excludes Management.
  - Worker binding controls still use role-aware filtering.
  - Main Video primary defaults secondary path to Backup Video when path redundancy is enabled.
  - Backup Video primary defaults secondary path to Main Video.
  - DMZ Video primary defaults secondary path to DMZ Video.
  - Manual secondary endpoint override is preserved.
- Compose validation
  - `docker compose --env-file .env.production.single-server.example -f docker-compose.production.yml config`
  - `docker compose --env-file .env.production.control-plane.example -f docker-compose.production.yml config`
  - `docker compose --env-file .env.production.primary.example -f docker-compose.production.yml config`
  - `docker compose --env-file .env.production.backup.example -f docker-compose.production.yml config`
- Full regression:
  - `docker compose -f docker-compose-microservices.yml exec -T api python -m pytest`

If the local API container lacks test dependencies after rebuild, install `requirements-test.txt` in the container before running pytest.

## Manual QA Recommendations

Ask QA to validate:

- `/api/interfaces` returns all four zones with normalized fields.
- Management does not appear in route source/destination dropdowns.
- Main Video input to DMZ Video output can be configured.
- DMZ Video input to Main Video output can be configured.
- Path redundancy from Main Video defaults secondary path to Backup Video.
- Path redundancy from Backup Video defaults secondary path to Main Video.
- Path redundancy from DMZ Video defaults secondary path to DMZ Video.
- Existing services with saved bind IPs still hydrate correctly.
- Production compose binds UDP only to configured IPs and ranges.

## Out Of Scope

- Linux Netplan/NIC IP editing.
- Authentication/authorization redesign.
- Automatic failback.
- SRT Rendezvous.
- Redis/Postgres HA redesign beyond docs and deployment guidance.
- Runtime FFmpeg structured mapping beyond what is necessary to preserve current behavior.

## Implementation Notes

- Keep changes additive and compatible.
- Do not remove legacy `network`, `node_roles`, `local_bind_ip`, `backup_input_ip`, `worker_1`, or flat service fields.
- Avoid hidden UI behavior that changes existing saved services on edit.
- Bump frontend asset query strings in `frontend/index.html` if `frontend/app.js` or `frontend/style.css` changes.
- Keep server-local compose warning in mind: production examples may change, but operators must still keep local env files separate from tracked examples.

## Handoff To QA

When implementation is done, report:

- Files changed.
- Exact compose config commands run.
- Exact pytest commands run.
- Any skipped checks.
- Any operational caveats for single-server or multi-server deployment.

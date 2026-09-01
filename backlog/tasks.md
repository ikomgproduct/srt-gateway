# SRT Gateway Backlog

## Current Priority: Network-Zone Architecture Planning

### 12. Architect Network-Zone Interface And Compose Model

Status: Implemented - Ready For Review

Goal:

- Define the technical plan for site-standard network separation across Main Video, Backup Video, DMZ Video, and Management networks.

Requirements:

- Use `docs/network-zone-product-handoff.md` as the Product Lead handoff.
- Model worker role, network zone, and route direction as separate concepts.
- Keep Management out of media source/destination dropdowns.
- Allow DMZ Video for both input and output on primary and backup workers.
- Define Main Video and Backup Video paired internal path behavior.
- Define whether paired path selection is automatic, operator-editable, or both.
- Define a richer interface inventory schema with NIC name, IP, zone, purpose, directions, and worker role eligibility.
- Define production compose/env strategy for publishing worker UDP ports on multiple video IPs.
- Keep port ranges env-configurable.
- Cover single-server HA and multi-server HA.
- Preserve lab compatibility for fewer NICs or shared IPs.
- Preserve the existing Route Editor V2 structured contract and flat compatibility fields.

Acceptance:

- Architecture doc has a network-zone section suitable for Dev Lead handoff.
- Product brief and agent context agree on Main Video, Backup Video, DMZ Video, and Management purposes.
- Architect plan calls out DMZ UI/Grafana exposure risk and direct-bind vs reverse-proxy choice.
- Architect plan identifies files likely affected and test coverage required.

Implementation notes:

- Architect handoff prepared in `docs/network-zone-architect-handoff.md`.
- Dev Lead implementer instructions prepared in `docs/network-zone-dev-lead-implementer-instructions.md`.
- Dev Lead resolved the open technical questions:
  - Use explicit optional Compose mappings or an override-file strategy; do not rely on comma-delimited env expansion for YAML port lists.
  - Normalize interface inventory in `/api/interfaces`.
  - Apply Main/Backup pairing defaults only to route path redundancy in this slice.
- Implemented API inventory normalization and zone-aware built-in defaults.
- Implemented zone-aware route endpoint dropdown filtering while preserving role-aware worker binding controls.
- Implemented path redundancy pairing defaults for Main Video, Backup Video, and DMZ Video without changing worker target semantics.
- Added `docker-compose.production.video-zones.yml` for explicit DMZ UDP publish mappings.
- Updated production env examples, README, UI guide, architecture, and agent context for the four-zone model.
- Site model:
  - Main Video: `eno1`, `10.70.15.3`, internal video input/output.
  - Backup Video: `eno2`, `10.71.15.3`, internal video input/output.
  - DMZ Video: `eno3`, `10.75.51.40`, public/external video input/output.
  - Management: `eno4`, `10.75.15.3`, API, SSH, Grafana/admin, and internal control-plane communication.
- Product decision: DMZ Video is selectable for input/output on both workers.
- Product decision: Main Video and Backup Video should pair as redundant internal paths.
- Product decision: UI/Grafana user access comes through DMZ, but internal service communication remains on Management.
- Product decision: UI labels should group interfaces as Main Video, Backup Video, and DMZ Video for now.
- Product decision: worker UDP publish IPs and port ranges must be env-configurable.
- QA added `tests/test_production_network_zone_static.py` to guard the optional DMZ video-zone compose override, split single-server port ranges, four-zone env inventory examples, Management exclusion from media inventory, and operator documentation.
- QA verification: focused network/API/frontend tests passed with `43 passed`; full regression passed with `90 passed`; production compose renders passed for single-server, control-plane, primary, backup, and video-zone override variants.

## Previous Priority: Route Editor V2 Product And Architecture Planning

### 6. Capture Engineering Feedback For Route Editor V2

Status: Done

Goal:

- Convert engineering feedback from `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf` into durable product and architecture context for future implementation.

Requirements:

- Treat the route editor as a protocol-aware Source/Destination workflow.
- Defer SRT `Rendezvous`.
- Support SRT `Listener` and `Caller` behavior.
- Support UDP `Unicast` and `Multicast` behavior.
- Separate network/link parameters from protocol-specific parameters.
- Model path redundancy as an explicit secondary interface/address/port row.
- Add SRT Stream ID behavior with `default` builder mode and `custom` raw mode.
- Reuse Stream ID behavior for SRT input and SRT destination.
- Keep Linux Netplan write management out of this slice; track it as a separate Network administration feature.

Acceptance:

- Product brief records Route Editor V2 requirements.
- Architecture doc records the structured contract direction and compatibility expectation.
- Agent context records the key decisions for future agents.
- Backlog identifies the next architecture task.

Implementation notes:

- Product decision: SRT `Rendezvous` is deferred.
- Product decision: Netplan write operations are future/high-risk and require dedicated safety design.
- Current PDF should remain in `docs/` or its requirements should be copied into docs before sharing work with other machines.

### 7. Architect Route Editor V2 Technical Plan

Status: Done

Goal:

- Produce the concrete technical plan for protocol-aware route creation/editing and the matching API/FFmpeg contract.

Requirements:

- Define structured source and destination schema additions.
- Define compatibility behavior for existing flat fields.
- Define FFmpeg mapping for UDP input/output, SRT listener/caller input/output, RTMP, RIST, HLS source, and generated HLS outputs.
- Define UI field visibility rules by protocol and mode.
- Define path redundancy behavior separately from worker primary/backup targeting.
- Define SRT Stream ID builder fields and serialization.
- Define tests for schema validation, UI serialization, FFmpeg command generation, worker execution, and compatibility.

Acceptance:

- Architecture doc names files likely affected and migration strategy.
- Architecture doc defines which fields are stored as structured config and which legacy fields are derived or preserved.
- Architecture doc states out-of-scope items: SRT `Rendezvous`, Netplan write management, automatic failback.
- Dev Lead can review the plan and prepare an implementer handoff without rereading the PDF.

Implementation notes:

- Additive migration is required. Do not remove or break existing flat payloads.
- New structured models should be normalized into one internal route shape before FFmpeg command construction.
- Frontend should serialize structured config and derived compatibility fields during the transition.
- `node_bindings` remains worker-role binding; path redundancy gets its own endpoint model.
- Product scope map for Architect follow-up: `docs/route-editor-v2-product-scope-map.md`.
- Dev Lead gaps resolved in `docs/route-editor-v2-implementer-handoff.md`: `destinations` default factory, multi-destination behavior, Stream ID derivation template, and normalization helper location.
- Dev Lead handover prepared in `docs/route-editor-v2-dev-lead-handover.md`.
- Dev Lead approved implementation scope and prepared implementer instructions in `docs/route-editor-v2-dev-lead-implementer-instructions.md`.

### 8. Implement Route Editor V2 Structured Contract

Status: QA Passed - Ready For Commit

Goal:

- Add the API and backend foundation for protocol-aware source/destination configuration.

Requirements:

- Add reusable schema models for endpoints, link parameters, SRT parameters, Stream ID config, source config, and destination config.
- Accept both legacy flat payloads and structured Route Editor V2 payloads.
- Derive compatibility fields from structured config when needed.
- Keep current Redis/Postgres desired config flow intact.
- Keep existing worker leasing and target-node behavior intact.

Acceptance:

- Existing flat service payload tests continue passing.
- New structured SRT listener/caller and UDP unicast/multicast payloads validate.
- Structured payloads produce expected legacy compatibility fields or normalized runtime config.
- Invalid combinations are rejected clearly, including missing ports for non-HLS network sources.

Implementation notes:

- Use `docs/route-editor-v2-implementer-handoff.md` as the implementer handoff.
- Use `docs/route-editor-v2-dev-lead-implementer-instructions.md` as the Dev Lead execution checklist.
- Keep this slice backend/API-focused; defer full UI and FFmpeg expansion to items 9 and 10.
- `TS over RTP` is product-captured but deferred from this implementation slice.
- Persist structured `source` and `destinations` as JSON columns so the contract can round-trip in API responses.
- Implemented structured schemas in `api/schemas.py`.
- Added pure normalization helpers in `api/route_normalizer.py`.
- Added `source` and `destinations` JSON columns in `api/models.py`.
- Added PostgreSQL startup column bootstrap for `source` and `destinations` in `api/main.py`.
- Create/update API paths normalize payloads before persistence and Redis sync.
- Dev Lead review fixes added: enabled structured destinations now require a usable target, and enabled path redundancy now requires manual mode plus a secondary endpoint with a port.
- Added `tests/test_route_editor_v2_contract.py`.
- QA added the Dev Lead suggested path-redundancy mode regression test.
- Verification: rebuilt API image, installed `requirements-test.txt` in the running API container, and ran `docker compose -f docker-compose-microservices.yml exec -T api python -m pytest`; latest result `79 passed`.

### 9. Implement Route Editor V2 UI

Status: Implemented - Ready For Review

Goal:

- Replace the current flat create/edit form with protocol-aware Source and Destination sections.

Requirements:

- Show only fields relevant to selected protocol and mode.
- Add UDP unicast/multicast controls.
- Add SRT listener/caller controls.
- Add default/custom Stream ID builder.
- Add explicit path redundancy secondary endpoint rows.
- Preserve edit hydration for existing legacy services.

Acceptance:

- Operators can create and edit UDP and SRT routes without touching raw URL fields for normal cases.
- Existing services still open correctly in edit mode.
- Hidden fields do not submit stale protocol data.
- Form remains usable on desktop and mobile.

Implementation notes:

- Architect handoff is captured in `docs/route-editor-v2-ui-architect-handoff.md`.
- Keep this item frontend-focused; backend FFmpeg structured mapping remains backlog item 10.
- The UI should serialize structured `source` and `destinations` while preserving flat compatibility fields for current workers.
- Implemented Route Editor V2 modal sections: Basics, Source, Destination, HLS Output, Worker Target And Bindings, and Advanced Compatibility.
- Source protocol visibility now covers SRT, UDP, RTMP, RIST, and HLS.
- Destination protocol visibility now covers SRT, UDP, RTMP, RTMPS, RIST, and raw URL compatibility.
- Added UDP unicast/multicast controls, SRT listener/caller controls, default/custom Stream ID controls, and SRT destination manual path redundancy fields.
- Submit payload now includes structured `source` and one enabled normal `destinations[]` object plus legacy flat compatibility fields.
- Edit hydration prefers structured `source` / `destinations` and falls back to flat legacy values.
- `pbkeylen` is submitted only as top-level legacy compatibility, not inside structured `source.srt` or `destinations[].srt`.
- QA browser cache finding fixed by version-tagging `style.css` and `app.js` in `frontend/index.html`.
- QA mobile grid overflow finding fixed by removing the inline `hardwareNodeRow` two-column override and keeping the dashboard/modal layout responsive through CSS.
- Reviewer compatibility findings fixed by preserving existing legacy target nodes during edit and preventing hidden legacy Stream ID values from leaking into non-custom/non-SRT submissions.
- Verification: `docker compose -f docker-compose-microservices.yml exec -T api python -m pytest tests/test_frontend_static.py`, `docker compose -f docker-compose-microservices.yml exec -T api python -m pytest tests/test_route_editor_v2_contract.py`, browser protocol visibility/reviewer-fix smoke tests, and `docker compose -f docker-compose-microservices.yml exec -T api python -m pytest` all passed.

### 10. Implement Route Editor V2 FFmpeg Mapping

Status: Future

Goal:

- Build FFmpeg input/output URLs from the normalized structured route contract.

Requirements:

- Map SRT listener/caller input and output binding behavior.
- Map UDP input/output binding behavior and multicast/unicast params.
- Preserve RTMP/RTMPS output behavior with `-f flv`.
- Preserve HLS source and generated HLS output behavior.
- Keep RIST behavior compatible until richer RIST requirements are confirmed.

Acceptance:

- Builder tests cover SRT listener/caller input and output.
- Builder tests cover UDP unicast/multicast input and output.
- Existing RTMP, HLS, and legacy binding tests continue passing.
- Worker tests confirm structured configs start only on eligible worker roles.

### 11. Design Network Administration Feature

Status: Future

Goal:

- Define a safe product and technical design for viewing and managing server NIC/IP settings separately from Route Editor V2.

Requirements:

- Show installed NICs and current IP configuration.
- Define whether and how operators can edit IP, gateway, DNS, and route settings.
- Persist approved changes through Linux Netplan.
- Protect management access so operators cannot easily lock themselves out.
- Include backup, validation, rollback, and explicit operator confirmation.

Acceptance:

- Product Lead defines user workflow and permissions.
- Architect defines Netplan interaction, safety checks, rollback behavior, and deployment constraints.
- Implementer receives a separate scoped task; this must not be bundled into Route Editor V2.

## Previous Priority: Production Compose Cleanup Before QA

### 0. Make Production Compose Canonical

Status: Done

Goal:

- Support production HA on either one physical server or multiple physical servers without relying on legacy/lab compose files.

Requirements:

- Keep `docker-compose.production.yml` as the production HA contract.
- Support single-server, control-plane, primary-worker, and backup-worker profiles via env files.
- Keep Redis/Postgres Docker-internal for single-server mode.
- Require management-network Redis/Postgres and shared preview storage for multi-server mode.
- Mark older compose files as lab/legacy.

Acceptance:

- Production compose renders for single-server, control-plane, primary worker, and backup worker env examples.
- Multi-server env examples include `PREVIEW_STORAGE`.
- README and architecture docs point production users to `docker-compose.production.yml`.

Implementation notes:

- `PREVIEW_STORAGE` controls the `/app/frontend/previews` mount.
- Single-server uses Docker named volume `shared_previews`.
- Multi-server examples use `/mnt/srt-gateway/previews` as the shared storage path.
- Old compose files now carry top-of-file lab/legacy warnings.

## Previous Priority: Address Dev Lead Review Before QA

### 1. Replace Binding Free Text With Interface Inventory Dropdowns

Status: Done

Goal:

- Align UI with product direction for installed hardware/interface selection.

Requirements:

- Add a configured interface inventory source, initially static config/env or JSON.
- Add API endpoint for available bind interfaces.
- Replace primary/backup input/output free-text fields with dropdowns.
- Hide `worker_1` binding controls from production UI.
- Keep backend compatibility for `worker_1`, `local_bind_ip`, and existing services.
- Preserve existing explicit `node_bindings` values when editing.

Acceptance:

- User can select primary input/output and backup input/output interfaces from dropdowns.
- Dropdown labels include friendly name and IP.
- Services still save `node_bindings.primary.input_bind_ip`, `node_bindings.primary.output_bind_ip`, `node_bindings.backup.input_bind_ip`, and `node_bindings.backup.output_bind_ip`.
- No visible single-worker binding section in production create/edit UI.

Implementation notes:

- `/api/interfaces` returns configured interface inventory.
- `INTERFACE_INVENTORY_JSON` can override the built-in primary/backup defaults.
- Legacy `worker_1` and `local_bind_ip` remain accepted by backend compatibility paths.

### 2. Add Full HLS Operational Guardrails

Status: Done

Goal:

- Make Full HLS safer for production use.

Requirements:

- Add explicit HLS storage path configuration.
- Define cleanup behavior for stopped/deleted services and rolling buffers.
- Add disk-capacity and buffer-size validation or at least conservative limits.
- Consider limiting number of simultaneous Full HLS services.
- Document CPU/GPU and storage impact.

Acceptance:

- Full HLS cannot silently consume unbounded disk.
- Buffer duration remains capped at 24 hours.
- Operators see clear resource guidance.
- Stopped/deleted services do not leave uncontrolled HLS artifacts.

Implementation notes:

- `MAX_FULL_HLS_SERVICES` limits simultaneous full HLS services.
- Disabled Full HLS service templates do not count against `MAX_FULL_HLS_SERVICES` until start or enable time.
- `/api/services/{id}/start` rejects starting a disabled Full HLS template when the active/intended service limit is already reached.
- `HLS_MIN_FREE_BYTES` blocks HLS startup when free space is too low.
- `HLS_STORAGE_QUOTA_BYTES` can reject oversized estimated HLS storage.
- Generated `low_res` and `full_res` HLS output directories are cleaned when services stop.
- Production compose now uses disk-backed `shared_previews` storage and carries explicit HLS guardrail environment defaults.

### 3. Correct HLS Master Playlist Metadata

Status: Done

Goal:

- Ensure generated master playlist metadata matches actual FFmpeg output.

Options:

- Remove hard-coded `RESOLUTION` values from master playlists.
- Or generate fixed-width scale expressions matching advertised dimensions.
- Or generate playlists after probing output dimensions.

Acceptance:

- Master playlist metadata is valid for non-16:9 input.
- Tests cover non-16:9-safe behavior.

Implementation notes:

- Master playlists no longer write hard-coded `RESOLUTION` attributes while FFmpeg uses dynamic width scaling.

### 4. Pass Node Role Through Legacy Stream Manager

Status: Done

Goal:

- Keep standalone/legacy path consistent with worker microservice binding behavior.

Requirement:

- Call `build_ffmpeg_command(..., node_role=self.node_role)` from `backend.stream_manager.StreamManager`.

Acceptance:

- Output binding behavior is consistent across worker and legacy stream manager paths.
- Test covers node-specific output binding in the legacy path or builder call.

Implementation notes:

- `StreamManager.start_service()` now calls `build_ffmpeg_command(..., node_role=self.node_role)`.
- `tests/test_stream_logic.py` covers the legacy builder call contract.

### 5. Resize And Structure Create/Edit Modal

Status: Done

Goal:

- Make the new service form fit comfortably after HLS and binding additions.

Requirements:

- Move modal sizing from inline styles to CSS.
- Increase desktop max width.
- Keep mobile responsive.
- Consider grouped sections for Basics, Source, Destination, Worker/Bindings, and Advanced.

Acceptance:

- Form fits without cramped layout on desktop.
- No overlapping controls on mobile.
- Save/cancel remains easy to reach.

Implementation notes:

- Modal width moved to CSS and now uses `min(960px, calc(100vw - 32px))`.
- Modal body scrolls within viewport height.
- Form rows collapse to single-column layout on narrow screens.

## Later Improvements

### HLS Source Optimization

Status: Future

- Detect when HLS input already contains compatible renditions.
- Cache or repackage compatible HLS instead of transcoding where safe.

### Automatic Failback

Status: Future

- Investigate guarded automatic failback.
- Avoid flapping after primary worker recovery.

### Production Compose Hardening

Status: Future

- Keep explicit production compose separate.
- Bind API/UI and Grafana only to management IPs.
- Keep Redis/Postgres internal for single-server deployment; expose only when required for multi-server HA.

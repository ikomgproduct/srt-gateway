# SRT Gateway Backlog

## Current Priority: Address Dev Lead Review Before QA

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
- Disabled Full HLS service templates do not count against `MAX_FULL_HLS_SERVICES`.
- `HLS_MIN_FREE_BYTES` blocks HLS startup when free space is too low.
- `HLS_STORAGE_QUOTA_BYTES` can reject oversized estimated HLS storage.
- Generated `low_res` and `full_res` HLS output directories are cleaned when services stop.

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

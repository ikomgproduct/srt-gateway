# Route Editor V2 Dev Lead Implementer Instructions

## Verdict

Approved for implementation with strict scope control.

Implement backlog item 8 only: Route Editor V2 Structured Contract.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Source Documents

Read these before editing:

- `.agent-context.md`
- `backlog/tasks.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `docs/route-editor-v2-product-scope-map.md`
- `docs/route-editor-v2-implementer-handoff.md`

The engineering PDF is useful background, but the docs above now contain the actionable requirements:

- `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf`

## Implementation Scope

Implement backend/API structured contract foundation only.

Required:

- Add Route Editor V2 schema models.
- Add a small pure normalization module at `api/route_normalizer.py`.
- Add persistence support for structured `source` and `destinations`.
- Preserve current flat API fields and behavior.
- Derive flat compatibility fields from structured input where safe.
- Add validation and normalization tests.
- Update project context docs after implementation.

Out of scope:

- UI rebuild.
- Broad FFmpeg runtime rewrite.
- Runtime path redundancy behavior.
- Multi-output FFmpeg support.
- Linux Netplan/NIC write management.
- SRT `Rendezvous`.
- `TS over RTP` runnable service support.
- Automatic failback.
- Production compose changes.
- Removing legacy flat fields or `worker_1` compatibility.

## Required Files To Change

Expected:

- `api/schemas.py`
- `api/main.py`
- `api/models.py`
- `api/route_normalizer.py`
- `tests/test_api_validation.py` or a new focused test file such as `tests/test_route_editor_v2_contract.py`
- `.agent-context.md`
- `docs/architecture.md`
- `backlog/tasks.md`

Possible, only if needed:

- `backend/models.py`
- `backend/ffmpeg_builder.py`

Avoid:

- `frontend/index.html`
- `frontend/app.js`
- `frontend/style.css`
- Docker/compose/env files

## Persistence Requirement

Current `ServiceModel` does not have `source` or `destinations` columns. Since the structured contract must round-trip through API responses, add JSON columns:

- `source = Column(JSON, nullable=True)`
- `destinations = Column(JSON, nullable=True)`

Update `ensure_schema_columns()` in `api/main.py` for PostgreSQL:

- `ALTER TABLE services ADD COLUMN IF NOT EXISTS source JSONB`
- `ALTER TABLE services ADD COLUMN IF NOT EXISTS destinations JSONB`

Do not add a heavy migration framework in this slice.

## Schema Guidance

Use `Field(default_factory=list)` for `destinations`.

Keep existing fields on `ServiceConfigRequest`.

Add structured models from `docs/route-editor-v2-implementer-handoff.md`, with conservative validation:

- `RouteEndpoint`
- `PathRedundancy`
- `LinkParameters`
- `StreamIdConfig`
- `SrtParameters`
- `SourceConfig`
- `DestinationConfig`

Use `extra="forbid"` on new models unless an existing compatibility path requires otherwise.

Do not add `rtp` or `rendezvous` to runnable service literals yet.

## Normalization Guidance

Create `api/route_normalizer.py`.

Keep it pure and directly testable. It should not depend on the database, Redis, FastAPI request state, or frontend code.

Expected helper behavior:

- Build structured source from flat legacy fields when `source` is missing.
- Build structured destination from `destination_url` when `destinations` is missing.
- Derive flat fields from structured `source` and `destinations`.
- Reject more than one enabled normal destination.
- Preserve HLS-only output behavior.
- Preserve legacy `streamid` when default Stream ID mode has no confirmed template.
- Derive legacy `streamid` only from custom Stream ID `custom_value`.

Suggested helper names:

- `normalize_service_payload(data: dict) -> dict`
- `derive_legacy_fields(data: dict) -> dict`
- `build_legacy_destination_url(destination: dict) -> str`

Keep naming consistent with local style if a cleaner pattern appears during implementation.

## API Behavior

In `create_service()` and `update_service()`:

- Validate request with `ServiceConfigRequest`.
- Convert to dict.
- Normalize before creating/merging `ServiceModel`.
- Persist both structured fields and derived flat fields.
- Sync Redis with the normalized persisted config.
- Return the normalized config.

In `service_to_dict()`:

- Include `source` and `destinations` if present.
- Avoid returning SQLAlchemy internal state.
- Preserve current response shape for existing frontend/API clients.

## Validation Rules

Must accept:

- Existing flat SRT payloads.
- Existing flat UDP payloads.
- Existing RTMP destination payloads.
- Existing HLS source payloads.
- Existing HLS-output-only payloads.
- Existing `node_bindings`.
- Existing `worker_1`, `local_bind_ip`, and `backup_input_ip`.

Must reject:

- SRT `Rendezvous`.
- `TS over RTP` or `rtp` as a runnable service protocol.
- More than one enabled normal destination.
- Missing non-HLS network source port.
- HLS source without `source_url` or structured `source.url`.
- Structured destination with no usable URL or endpoint when normal output is required.

## Test Requirements

Add or update tests for:

- Legacy flat payloads still pass.
- Unknown fields are still rejected.
- Structured SRT listener source derives flat fields.
- Structured SRT caller source derives flat fields.
- Structured UDP unicast source derives flat fields.
- Structured UDP multicast source derives flat fields.
- Structured SRT custom Stream ID derives legacy `streamid`.
- Structured SRT default Stream ID does not invent a legacy `streamid`.
- Structured UDP destination derives `udp://...`.
- Structured SRT destination derives `srt://...`.
- More than one enabled normal destination is rejected.
- `rendezvous` is rejected.
- `rtp` / `TS over RTP` is rejected for runnable services.
- Structured fields round-trip in API response.
- Structured fields are present in Redis desired config if the service is saved.

## Verification

Run:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
```

If containers are not running, report that clearly and run the narrowest available local checks only if the environment supports them.

## Completion Notes

After implementation:

- Update `.agent-context.md` with actual implementation state.
- Update `docs/architecture.md` with final field names/helper names if they differ.
- Update `backlog/tasks.md` with item 8 status and notes.
- Do not mark UI or FFmpeg mapping items done.

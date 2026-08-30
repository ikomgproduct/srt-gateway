# Route Editor V2 Implementer Handoff

## Goal

Implement the first Route Editor V2 slice: the structured API/backend contract and normalization foundation.

This slice should not replace the UI yet and should not rewrite FFmpeg behavior broadly. The purpose is to make the backend ready to accept a protocol-aware route model while preserving all existing flat service payloads and worker behavior.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Context

Engineering feedback was captured from:

- `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf`

Relevant project context:

- `.agent-context.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `docs/route-editor-v2-product-scope-map.md`
- `backlog/tasks.md`

Important decisions:

- SRT `Rendezvous` is deferred.
- SRT scope for this work is `Listener` and `Caller`.
- UDP must support `Unicast` and `Multicast`.
- `TS over RTP` appears in the product scope map but is deferred from this implementation slice until FFmpeg/runtime behavior is designed.
- Path redundancy is separate from worker primary/backup ownership.
- `node_bindings` remains worker-role input/output binding.
- Legacy flat payloads must continue to work.
- Linux Netplan write management is out of scope.
- Automatic failback is out of scope.

## Scope For This Implementer Task

Implement backlog item 8 only: Route Editor V2 Structured Contract.

Do:

- Add structured schema models in `api/schemas.py`.
- Add normalization helpers that produce one internal route shape from either legacy flat payloads or structured V2 payloads.
- Preserve existing `ServiceConfigRequest` fields and validation behavior.
- Accept structured source/destination config in addition to existing flat fields.
- Derive legacy compatibility fields from structured config where needed.
- Ensure persisted config and Redis desired config remain compatible with current workers.
- Add tests for validation and normalization.

Do not:

- Replace the current UI form.
- Implement the full Route Editor V2 UI.
- Implement path redundancy runtime behavior beyond schema/normalization.
- Change Linux network configuration or Netplan.
- Add SRT `Rendezvous`.
- Add `TS over RTP` runtime/API acceptance for runnable services.
- Remove `worker_1`, `local_bind_ip`, `backup_input_ip`, or existing flat API fields.
- Change production compose behavior.

## Proposed Data Models

Add reusable Pydantic models with conservative defaults and `extra="forbid"` unless compatibility requires otherwise.

Suggested models:

- `RouteEndpoint`
  - `interface_id: Optional[str]`
  - `bind_ip: Optional[str]`
  - `address: str`
  - `port: Optional[int]`

- `PathRedundancy`
  - `enabled: bool = False`
  - `mode: Literal["none", "manual"] = "none"`
  - `secondary_endpoint: Optional[RouteEndpoint]`

- `LinkParameters`
  - `mtu: Optional[int]`
  - `ttl: Optional[int]`
  - `tos: Optional[str]`
  - `fec: Optional[str]`
  - `max_bitrate_kbps: Optional[int]`
  - `traffic_shaping: bool = False`

- `StreamIdConfig`
  - `mode: Literal["default", "custom"] = "default"`
  - `host_mode: Optional[str]`
  - `resource_name: Optional[str]`
  - `username: Optional[str]`
  - `custom_value: Optional[str]`

- `SrtParameters`
  - `latency_ms: Optional[int]`
  - `receive_buffer_bytes: Optional[int]`
  - `retransmission_bandwidth_kbps: Optional[int]`
  - `encryption: Optional[str]`
  - `passphrase: Optional[str]`
  - `authentication: Optional[str]`
  - `rtp_header: Optional[str]`
  - `error_correction: Optional[str]`
  - `stream_id: Optional[StreamIdConfig]`

- `SourceConfig`
  - `protocol: Literal["srt", "udp", "rtmp", "rist", "hls"]`
  - `mode: Optional[Literal["listener", "caller"]]`
  - `type: Optional[Literal["unicast", "multicast"]]`
  - `primary_endpoint: Optional[RouteEndpoint]`
  - `path_redundancy: Optional[PathRedundancy]`
  - `link_parameters: Optional[LinkParameters]`
  - `srt: Optional[SrtParameters]`
  - `url: Optional[str]`
  - `path: str = ""`

- `DestinationConfig`
  - `protocol: Literal["srt", "udp", "rtmp", "rtmps", "rist", "raw"]`
  - `mode: Optional[Literal["listener", "caller"]]`
  - `type: Optional[Literal["unicast", "multicast"]]`
  - `primary_endpoint: Optional[RouteEndpoint]`
  - `path_redundancy: Optional[PathRedundancy]`
  - `link_parameters: Optional[LinkParameters]`
  - `srt: Optional[SrtParameters]`
  - `url: Optional[str]`
  - `enabled: bool = True`

Add optional fields to `ServiceConfigRequest`:

- `source: Optional[SourceConfig]`
- `destinations: list[DestinationConfig] = Field(default_factory=list)`

For this slice, the `destinations` list is a future-compatible API shape, not full multi-output runtime support.

## Normalization Rules

Create a helper that normalizes config into a runtime-friendly shape. Keep it close to the API/backend model layer, not the frontend.

Required behavior:

- If no structured `source` is provided, build normalized source from existing flat fields.
- If structured `source` is provided, validate it and derive:
  - `source_protocol`
  - `source_mode`
  - `source_ip`
  - `source_port`
  - `source_path`
  - `source_url`
  - `latency_ms`
  - `passphrase`
  - `streamid`
- If no structured `destinations` are provided, build normalized destination from `destination_url`.
- If structured `destinations` are provided, derive `destination_url` from the first enabled normal destination where possible.
- Reject payloads with more than one enabled normal destination until multi-output FFmpeg/runtime behavior is implemented.
- Preserve disabled extra destination objects only if doing so does not complicate persistence or response behavior; otherwise reject extra destinations clearly for this slice.
- Preserve existing HLS behavior: `destination_url` can be empty only when low-res or full HLS output is enabled.
- For HLS source, require `source.url` or legacy `source_url`.
- For non-HLS network sources, require a port.
- Reject SRT mode values other than `listener` and `caller`.
- Reject unsupported protocol/mode combinations with clear validation messages.

Normalization helper location:

- Prefer a new small module `api/route_normalizer.py` for conversion helpers so `api/schemas.py` remains focused on validation models.
- `ServiceConfigRequest` validators may call local helper methods for simple field derivation, but URL construction/parsing and structured-to-flat conversion should live in `api/route_normalizer.py`.
- Keep the helper pure and directly testable.

Stream ID derivation:

- For `StreamIdConfig.mode == "custom"`, derive legacy `streamid` from `custom_value`.
- For `StreamIdConfig.mode == "default"`, validate and persist the structured fields but do not derive a legacy `streamid` string in this slice unless Product/Architect confirms the exact template.
- If legacy `streamid` is supplied alongside a default structured Stream ID, preserve the legacy value for runtime compatibility.

## Compatibility Requirements

Existing API clients must still work.

Must remain valid:

- Existing flat SRT service payloads.
- Existing flat UDP service payloads.
- Existing RTMP destination payloads.
- Existing HLS-source payloads.
- Existing HLS-output-only payloads.
- Existing `node_bindings`.
- Existing `worker_1` and `local_bind_ip` backend/lab compatibility.

Must not become valid yet:

- SRT `Rendezvous`.
- `TS over RTP` as a runnable service protocol.
- More than one enabled normal destination.

Responses during transition should include both:

- Existing flat fields.
- New structured fields when supplied or derived.

## Files Likely Affected

- `api/schemas.py`
- `api/main.py`
- `api/route_normalizer.py`
- `backend/models.py`
- `backend/ffmpeg_builder.py`, only if a small normalization adapter is needed
- `tests/`

Avoid frontend changes in this slice unless a test fixture requires minor static compatibility.

## Verification Plan

Run the existing container test suite:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
```

Add focused tests for:

- Legacy flat SRT payload still validates.
- Legacy flat UDP payload still validates.
- HLS source still requires `source_url` or structured `source.url`.
- HLS-output-only service still allows empty `destination_url`.
- Structured SRT listener source validates and derives legacy fields.
- Structured SRT caller source validates and derives legacy fields.
- Structured UDP unicast source validates.
- Structured UDP multicast source validates.
- Structured SRT destination derives a valid `srt://` destination URL.
- Structured UDP destination derives a valid `udp://` destination URL.
- SRT `Rendezvous` is rejected.
- `TS over RTP` is rejected or explicitly unsupported for runnable services in this slice.
- More than one enabled normal destination is rejected clearly.
- Missing non-HLS port is rejected clearly.
- Path redundancy schema accepts a secondary endpoint but does not change worker targeting.

## Implementation Notes

- Prefer additive code over rewrites.
- Keep normalization small and testable.
- Keep field derivation deterministic.
- Do not change Redis key/channel behavior.
- Do not change worker lease behavior.
- Do not change production compose files.
- Update `.agent-context.md`, `docs/architecture.md`, and `backlog/tasks.md` after implementation to record what actually changed.

## Expected Handoff Result

When complete, Dev Lead should be able to review a backend/API-only structured contract foundation. QA should be able to verify existing services still work and new structured payloads are accepted, even before the UI is rebuilt.

# Route Editor V2 Dev Lead Handover

## Goal

Review the updated Architect handoff for Route Editor V2 Structured Contract before assigning implementation.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Context

Relevant files:

- `.agent-context.md`
- `docs/product-brief.md`
- `docs/architecture.md`
- `docs/route-editor-v2-product-scope-map.md`
- `docs/route-editor-v2-implementer-handoff.md`
- `backlog/tasks.md`

Engineering feedback source:

- `docs/RE_ SRT GW for testing - Adir Hadad - Outlook.pdf`

## Architect Updates Since Dev Lead Review

The Architect reviewed the Dev Lead and Product Lead concerns and updated the implementer handoff to close the implementation gaps.

Resolved Dev Lead comments:

- `destinations` must use `Field(default_factory=list)`.
- Route Editor V2 Structured Contract is not full multi-output support.
- Payloads with more than one enabled normal destination should be rejected clearly in this slice.
- `StreamIdConfig.mode == "custom"` derives legacy `streamid` from `custom_value`.
- `StreamIdConfig.mode == "default"` is persisted/validated but should not derive a legacy `streamid` string until the exact template is confirmed.
- Normalization helpers should live in a new small `api/route_normalizer.py` module.

Product scope preservation:

- Full product scope remains in `docs/route-editor-v2-product-scope-map.md`.
- The first implementer task stays backend/API-focused.
- UI, expanded FFmpeg behavior, runtime path redundancy, Netplan, automatic failback, and SRT `Rendezvous` remain out of scope.

Protocol decision:

- `TS over RTP` is captured in the product map because it appears in engineering feedback.
- `TS over RTP` is deferred from the first structured-contract implementation and should not be accepted as a runnable service protocol yet.

## Dev Lead Review Request

Please review whether the updated handoff is now safe to give to Implementer for backlog item 8.

Focus areas:

- Is the implementation slice still small enough?
- Are compatibility requirements strong enough for existing services?
- Is the structured model acceptable as an additive contract?
- Are validation rules clear enough?
- Are tests sufficient before touching UI or FFmpeg runtime behavior?
- Should any item be moved out of backlog item 8 before implementation starts?

## Expected Dev Lead Output

Approve or request changes.

If approved, prepare the final implementer instruction for:

- Backlog item 8 only.
- API schema models.
- `api/route_normalizer.py`.
- Validation and normalization tests.
- No UI rewrite.
- No broad FFmpeg rewrite.

## Verification Expected After Implementation

The Implementer should run:

```powershell
docker compose -f docker-compose-microservices.yml exec -T api python -m pytest
```

The Implementer should also report any skipped checks if the local containers are not running.

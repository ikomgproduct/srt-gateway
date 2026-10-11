# Dynamic UDP Multicast Intake - QA Fix Implementation Summary

Date: 2026-10-07

## Goal

Resolve the QA-reported clean-image API startup failure without changing multicast behavior, Docker topology, route contracts, or user-visible functionality.

## Changed

- Added `greenlet==3.0.3` to `requirements.txt`.
- Retained `greenlet==3.0.3` in `requirements-test.txt`.
- No application, worker, frontend, schema, Compose, or network-policy code changed in this repair.

## Root Cause

The Dockerfile installs application dependencies from `requirements.txt`. Test runs installed `requirements-test.txt`, which included `greenlet`, but the runtime file did not. SQLAlchemy's async module therefore imported successfully in the test container while a clean application image entered a restart loop.

## Verification

- No-cache API image build: passed.
- Packaging regression: `1 passed`.
- Clean runtime import without test dependencies: passed with `runtime imports ok`.
- Full regression: `129 passed`.
- Fresh lab stack: API remained `Up` beyond 30 seconds; no restart loop.
- API log: application startup completed successfully with no import failure.
- UI root `/`: HTTP `200`.
- `/api/runtime-policy`: HTTP `200`, default multicast range `1024-65535`.
- `/api/interfaces`: HTTP `200`, Main Video, Backup Video, DMZ Video, and non-media Management inventory returned.
- `/api/workers`: HTTP `200`, local lab worker discovered.
- Frontend JavaScript syntax: passed.
- Production Compose render: passed for single-server, control-plane, primary worker, backup worker, and the no-op compatibility override.
- Lab stack was stopped after verification without deleting named volumes.

## Scope Notes

- The original failed QA report remains unchanged as historical evidence.
- This repair only unblocks the release image. Browser workflow checks and the physical Linux multicast matrix remain QA release gates.
- No Architect or Product Lead consultation was required because the fix did not change architecture or product behavior.

## Handoff

Implementation is ready for a short Dev Lead review and then QA rerun. QA should repeat clean-image startup and continue with browser/API and physical multicast testing from `docs/dynamic-multicast-port-dev-lead-qa-handoff.md`.

## Dev Lead Approval

Dev Lead independently verified the clean runtime import and full `129 passed` regression. The repair is approved for QA rerun; see `docs/dynamic-multicast-port-qa-fix-dev-lead-review.md`.

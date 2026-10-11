# Dynamic UDP Multicast Intake - Implementation Summary

## Goal

Allow production workers to receive UDP multicast on operator-selected policy-approved ports without publishing a broad Docker UDP range.

## Changed

- Added shared multicast policy helpers for IPv4 group detection, configurable port bounds, binding precedence, inventory validation, bind keys, and configuration fingerprints.
- Preserved legacy flat multicast intent during route normalization and carried structured source endpoints into worker runtime models.
- Added enabled create/update/start conflict checks and `GET /api/runtime-policy`.
- Added FFmpeg multicast `localaddr`, `reuse=1`, and structured endpoint precedence.
- Added worker local-interface preflight, stable error codes, retryability metrics, fingerprint suppression, configuration-change retry, and explicit retry.
- Connected stable FFmpeg bind/join stderr detection to the process monitor so recognized network errors remain non-retryable instead of collapsing to a generic exit code.
- Moved production workers to Linux host networking and removed worker UDP port publication.
- Added production Redis authentication, loopback/Management binding, and separate `WORKER_REDIS_URL`.
- Converted the video-zone override into a one-release no-op compatibility file.
- Updated the UI to apply runtime multicast port bounds and bumped frontend asset versions.

## Compatibility

- No database migration was added.
- Flat service fields remain accepted and synchronized to Redis.
- Lab and legacy Compose files were not changed.
- Disabled templates may overlap; conflicts are enforced when a route becomes running-intended.

## Automated Verification

- Focused multicast/API/worker/FFmpeg/compatibility suite: `77 passed` before the final additions.
- Focused worker monitor regression after the Dev Lead review fix: `9 passed`.
- Full regression after the Dev Lead review fix: `122 passed`.
- Frontend JavaScript syntax check passed.
- `git diff --check` passed with line-ending warnings only.
- Production Compose rendered for single-server, control-plane, primary-worker, backup-worker, and the compatibility override combination.

## Hardware QA Required

- Send MPEG-TS multicast on ports `1024`, `5500`, and `65535` through Main Video, Backup Video, and DMZ Video.
- Verify same-service primary/backup reception, active/passive lease ownership, restart/rejoin, conflict rejection, and stable invalid-interface/occupied-port errors.
- Verify API/UI and Grafana remain reachable while Redis and Postgres are unreachable from DMZ.

## Dev Lead Review

Dev Lead review is complete and the implementation is approved for QA. The executable QA scope, hardware matrix, failure checks, and release gates are recorded in `docs/dynamic-multicast-port-dev-lead-qa-handoff.md`.

## QA Result

The first QA cycle failed because a freshly built API image cannot start: `requirements.txt` omits the `greenlet` runtime dependency required by SQLAlchemy asyncio. The expanded suite reports `128 passed, 1 failed`, with the failure intentionally guarding that missing dependency. See `docs/dynamic-multicast-port-qa-report.md`.

Live browser/API and physical multicast validation remain blocked until the runtime image starts cleanly.

## QA Blocker Remediation

The runtime packaging blocker is fixed by adding `greenlet==3.0.3` to `requirements.txt`. A no-cache image build, clean runtime import, live API smoke test, production Compose rendering, frontend syntax check, and full `129 passed` regression now succeed. See `docs/dynamic-multicast-port-qa-fix-implementation-summary.md`.

Physical Linux multicast and final browser workflow validation remain required for QA release approval.

## QA Rerun

The corrected runtime image passed a no-cache build, clean async imports, the packaging guard, all production Compose renders, frontend syntax validation, live API smoke/boundary checks, and the full `129 passed` regression. The previous runtime packaging blocker is closed.

Release approval remains blocked pending production-like Linux multicast, HA/recovery, failure-stability, DMZ isolation, and normal-browser create/edit validation. See `docs/dynamic-multicast-port-qa-rerun-report.md`.

## Reviewer Follow-Up Implementation

The post-QA Reviewer corrections from `docs/dynamic-multicast-port-review-dev-lead-implementer-handoff.md` are implemented:

- `target_node: all` deterministically validates primary and backup, independent of submitted binding keys.
- Structured multicast endpoint `interface_id` resolves one exact video/input inventory entry and must match its endpoint bind IP.
- Resolved production role bindings are validated separately for primary/backup eligibility; legacy `worker_1` and `standalone` targets retain IP-based video/input compatibility.
- Disabled multicast templates now require valid group, port, interface identity, and resolved bindings while remaining exempt from enabled-claim conflicts.
- Enabled multicast create, update, and start admission is serialized by an API-local async lock and a PostgreSQL transaction-scoped advisory lock. Conflict query, persistence, and commit remain inside the guard; Redis synchronization remains post-commit.
- Production Compose requires `GRAFANA_ADMIN_PASSWORD`, and all four committed production env examples provide a placeholder.
- Obsolete current-production fixed worker-port publication guidance was removed.

Verification after these corrections:

- Full containerized regression: `148 passed`.
- Concurrent conflicting create coverage produces one success and one HTTP `422` under SQLite.
- PostgreSQL advisory-lock SQL and SQLite dialect gating tests pass.
- All five production Compose render paths pass.
- Production Compose fails as intended when `GRAFANA_ADMIN_PASSWORD` is empty.
- Frontend JavaScript syntax check passes.
- A no-cache API image build and clean runtime imports pass.

The reviewer corrections are ready for Dev Lead review. Physical Linux multicast, HA/rejoin, failure-stability, DMZ isolation, and normal-browser QA remain required after software review.

## Reviewer-Fix QA

Dev Lead approved the reviewer corrections and software QA completed the local
end-to-end cycle. The full regression reports `148 passed`; all production
Compose render paths, the mandatory Grafana-password failure, frontend syntax,
clean no-cache image build, and runtime imports pass.

Live PostgreSQL/Redis checks passed for disabled-template overlap, start-time
conflict rejection, exact interface validation, stable non-retryable failure,
post-commit desired-state synchronization, cleanup, and concurrent admission.
A real concurrent PostgreSQL HTTP create produced exactly one success and one
HTTP `422` for the same bind claim.

Browser QA passed protocol-aware field switching, Management exclusion,
structured multicast creation, persistence, and dashboard display. Final
release approval remains pending physical Linux multicast, HA/rejoin,
failure-stability, DMZ isolation, and normal-browser create/edit/reload checks.
See `docs/dynamic-multicast-port-review-qa-report.md`.

## Post-QA Reviewer Decision

Reviewer approved the release for production-like Linux hardware QA after an
independent `148 passed` regression. Final production release remains blocked
on the physical multicast, HA/rejoin, failure-stability, DMZ-isolation, and
normal-browser gates.

One non-blocking P2 remains: destination SRT Stream ID default/custom fields are
not gated by destination protocol and remain visible for non-SRT destinations.
Serialization remains protocol-safe. Fix and retest this visibility issue
before final release. See `docs/dynamic-multicast-port-post-qa-review.md`.

# Dynamic UDP Multicast Intake - QA Rerun Report

Date: 2026-10-07
Tested branch/commit: `main` / `7b5b8cd` plus the current uncommitted implementation changes

## Result

**Blocked - software QA passed; target-hardware and full browser validation remain required.**

The previous P1 runtime packaging failure is resolved. A no-cache API image installs `greenlet==3.0.3`, imports the SQLAlchemy async/API stack, starts normally, and passes the full automated suite. No new software blocker was found in the local API, Compose, or dependency checks.

Final release approval is still blocked because the required multicast, HA/recovery, failure-stability, and DMZ isolation matrix needs production-like Linux hardware. The available in-app browser rendered the dashboard and loaded the application assets/API data, but did not activate the inline New Service handler through automation; no Chrome automation target was available for an independent interaction check.

## Automated Results

| Check | Result | Evidence |
| --- | --- | --- |
| API image build without cache | Pass | `docker compose ... build --no-cache api` |
| Clean runtime imports | Pass | `greenlet`, `sqlalchemy.ext.asyncio`, and `api.main` imported from the rebuilt runtime image |
| Runtime dependency guard | Pass | `1 passed` |
| Full regression suite | Pass | `129 passed in 1.03s` |
| Frontend JavaScript syntax | Pass | `node --check frontend/app.js` |
| Production Compose renders | Pass | Single-server, control-plane, primary, backup, and single-server plus compatibility override |
| Whitespace validation | Pass | `git diff --check`; line-ending conversion warnings only |

## Live Stack And API Results

- API, database, Redis, worker, telemetry, Prometheus, and Grafana remained running after rebuild.
- `/` returned HTTP `200`.
- `/api/runtime-policy` returned multicast bounds `1024-65535`.
- `/api/interfaces` returned Main Video, Backup Video, DMZ Video, and Management inventory entries.
- `/api/workers` reported `worker_1`.
- API and worker startup logs contained no runtime errors.
- Disabled multicast templates were accepted on ports `1024`, `5500`, and `65535`.
- Port `65536` was rejected with HTTP `422`.
- An enabled route bound to the Management interface was rejected with HTTP `422` and `not an eligible video interface`.
- All QA-created service records were removed. The temporary stack was stopped without deleting volumes.

## Browser Result

| Scenario | Result | Notes |
| --- | --- | --- |
| Dashboard render | Pass | SRT Gateway dashboard and empty service table rendered |
| Frontend assets/API loading | Pass | `style.css`, `app.js`, node role, interfaces, runtime policy, and services returned successfully |
| Create/edit modal interaction | Blocked | The in-app automation target did not activate the inline New Service handler |
| Chrome cross-check | Blocked | No Chrome automation target was available in this QA environment |

This browser limitation is not classified as a product defect because the external script ran and populated API state, while the failure was isolated to automated activation of the inline handler. A normal supported browser must complete the create/edit workflow on the target system.

## Required Target-Hardware QA

- Send real MPEG-TS multicast on ports `1024`, `5500`, and `65535` through Main Video, Backup Video, and DMZ Video.
- Verify primary/backup reception, active-passive ownership, worker restart/rejoin, and reconciliation after missed events.
- Verify invalid interface, occupied port, and multicast join failures remain stable and do not cause watchdog restart storms.
- Verify configuration edits and explicit retry recover a corrected route.
- Verify Redis and Postgres are inaccessible from DMZ while API/UI and Grafana remain reachable at approved endpoints.
- Complete UI create/edit, protocol switching, interface filtering, policy bounds, and legacy/structured hydration in a normal supported browser.

## Recommendation

The implementation is ready for production-like target-hardware QA. Do not grant final release approval until the physical nine-case multicast matrix, HA/recovery checks, failure-stability observation, network-isolation checks, and normal-browser workflow pass.

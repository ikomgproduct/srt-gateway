# Dynamic UDP Multicast Intake - QA Report

Date: 2026-10-07

## Result

**Fail - release blocked by API runtime packaging.**

The multicast implementation and existing regression coverage pass in the test container, but a freshly built application image cannot start the API because the runtime dependency set does not install `greenlet`, which SQLAlchemy's async layer requires. The API enters a restart loop, the UI/API is unavailable, and hardware multicast QA cannot proceed against this build.

## Scope Reviewed

- Dev Lead QA handoff and acceptance gates.
- Implementer summary and current implementation diff.
- Multicast policy, normalization, API conflict validation, FFmpeg URL generation, worker preflight, error classification, retry suppression, UI policy handling, production Compose, and env examples.
- Local lab stack startup from freshly rebuilt images.

## Tests Added

- Runtime policy endpoint honors custom env bounds.
- API rejects a multicast port above a custom maximum.
- API rejects Management as a multicast media interface.
- Equal multicast ports on different bind IPs remain allowed.
- Non-numeric multicast policy env values are rejected.
- Worker process monitoring retains `invalid_bind_interface` as non-retryable.
- Production dependency regression requires `greenlet` in `requirements.txt`.
- `requirements-test.txt` now declares `greenlet` so the QA suite is reproducible.

## Automated Results

| Check | Result | Evidence |
| --- | --- | --- |
| Focused multicast/API/worker/frontend/Compose tests before packaging guard | Pass | `62 passed` |
| Full regression before packaging guard | Pass | `128 passed` |
| Full regression with packaging guard | Fail | `128 passed, 1 failed` |
| Frontend JavaScript syntax | Pass | `node --check frontend/app.js` |
| Single-server production Compose render | Pass | `docker compose ... config --quiet` |
| Control-plane production Compose render | Pass | `docker compose ... config --quiet` |
| Primary-worker production Compose render | Pass | `docker compose ... config --quiet` |
| Backup-worker production Compose render | Pass | `docker compose ... config --quiet` |
| Compatibility override Compose render | Pass | `docker compose ... config --quiet` |
| Fresh local stack API startup | Fail | API restarts with missing `greenlet` import error |
| Live API/UI checks | Blocked | Port `8000` is unavailable because API does not start |
| Physical Linux multicast matrix | Blocked | Requires a bootable release image on target Linux topology |

## Blocking Finding

### P1 - Clean API image cannot start

Reproduction:

```powershell
docker compose -f docker-compose-microservices.yml up -d --build
docker compose -f docker-compose-microservices.yml ps
docker compose -f docker-compose-microservices.yml logs --no-color --tail=80 api
```

Observed:

- API status repeatedly changes to `Restarting (1)`.
- The log reports `ModuleNotFoundError: No module named 'greenlet'` followed by SQLAlchemy's async dependency error.
- Requests to `/`, `/api/runtime-policy`, `/api/interfaces`, and `/api/workers` fail.

Expected:

- A clean image starts without installing test dependencies at runtime.
- API/UI is reachable on port `8000`.

Required correction:

- Add a compatible `greenlet` runtime dependency to `requirements.txt`, or install SQLAlchemy with its supported asyncio extra.
- Rebuild from the corrected dependency file; do not validate using an old image or an ad hoc package installation inside a running container.

Regression test:

- `tests/test_production_network_zone_static.py::test_runtime_dependencies_include_greenlet_for_async_sqlalchemy`

## Deferred Hardware Scenarios

After the API image starts, QA must still execute the Dev Lead handoff matrix on Linux:

- Ports `1024`, `5500`, and `65535` on Main Video, Backup Video, and DMZ Video.
- Primary/backup concurrent reception where configured.
- Active-passive lease ownership and worker restart/rejoin.
- Invalid interface, occupied port, and multicast-join failure without restart storms.
- Redis/Postgres isolation from DMZ and Management exclusion from media selectors.
- Browser create/edit hydration and runtime-policy bounds.

## Recommendation

Do not approve or release this build. Return it to the Implementer for the runtime dependency fix, then rerun the complete automated suite from a fresh image and continue with live browser/API and physical multicast QA.

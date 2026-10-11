# Dynamic UDP Multicast Intake - QA Fix Implementer Handoff

Date: 2026-10-07

## Goal

Fix the clean-image API startup failure reported by QA, prove that the shipped image boots without ad hoc package installation, and return backlog item 13 to QA for live browser/API and physical multicast validation.

## Dev Lead Verdict

**Request changes.**

The multicast implementation remains accepted. The release is blocked by one P1 runtime-packaging defect: the production image installs `requirements.txt`, which does not declare the `greenlet` dependency required by SQLAlchemy asyncio.

## Required Reading

- `docs/dynamic-multicast-port-qa-report.md`
- `docs/dynamic-multicast-port-dev-lead-qa-handoff.md`
- `docs/dynamic-multicast-port-implementation-summary.md`
- `.agent-context.md`
- `backlog/tasks.md`, item 13

## Root Cause

- `Dockerfile` installs only `requirements.txt` into application images.
- `requirements-test.txt` now includes `greenlet==3.0.3`, so tests that install the test dependencies can import SQLAlchemy asyncio.
- `requirements.txt` has plain `sqlalchemy` and no `greenlet` or `sqlalchemy[asyncio]` entry.
- A fresh API image therefore enters a restart loop with `ModuleNotFoundError: No module named 'greenlet'`.

## Required Implementation

1. Add `greenlet==3.0.3` to `requirements.txt`.
2. Keep `greenlet==3.0.3` in `requirements-test.txt` so test-only container runs remain reproducible.
3. Do not change Docker networking, Compose profiles, multicast policy, route schemas, UI behavior, Redis topology, or worker logic in this fix.
4. Do not work around the defect by installing packages manually in a running container.
5. Do not weaken or remove `test_runtime_dependencies_include_greenlet_for_async_sqlalchemy`.

The explicit runtime dependency is preferred over changing the existing unpinned `sqlalchemy` line to `sqlalchemy[asyncio]` in this narrow repair. A broader dependency-pinning pass may be planned separately after release validation.

## Verification

### 1. Packaging Regression

Run the focused guard:

```powershell
docker compose -f docker-compose-microservices.yml build --no-cache api
docker compose -f docker-compose-microservices.yml run --rm --no-deps api sh -c "pip install -q -r requirements-test.txt && python -m pytest -q tests/test_production_network_zone_static.py::test_runtime_dependencies_include_greenlet_for_async_sqlalchemy"
```

Expected: `1 passed`.

### 2. Clean Runtime Import

Use the freshly built application image without installing test packages:

```powershell
docker compose -f docker-compose-microservices.yml run --rm --no-deps api python -c "import greenlet; import sqlalchemy.ext.asyncio; import api.main; print('runtime imports ok')"
```

Expected: command exits successfully and prints `runtime imports ok`.

### 3. Full Regression

```powershell
docker compose -f docker-compose-microservices.yml run --rm --no-deps api sh -c "pip install -q -r requirements-test.txt && python -m pytest -q"
```

Expected baseline after the fix: `129 passed`.

### 4. Fresh Stack Smoke Test

```powershell
docker compose -f docker-compose-microservices.yml up -d --build
docker compose -f docker-compose-microservices.yml ps
docker compose -f docker-compose-microservices.yml logs --no-color --tail=100 api
```

Confirm the API remains `Up` rather than `Restarting`. Then verify:

```powershell
curl.exe -fsS http://localhost:8000/
curl.exe -fsS http://localhost:8000/api/runtime-policy
curl.exe -fsS http://localhost:8000/api/interfaces
curl.exe -fsS http://localhost:8000/api/workers
```

Observe the API container for at least 30 seconds and confirm no restart loop. Stop the lab stack after verification without deleting named data volumes:

```powershell
docker compose -f docker-compose-microservices.yml down
```

### 5. Production Configuration Regression

Render all supported production shapes and the compatibility override:

- `.env.production.single-server.example`
- `.env.production.control-plane.example`
- `.env.production.primary.example`
- `.env.production.backup.example`
- single-server plus `docker-compose.production.video-zones.yml`

Also run `node --check frontend/app.js` and `git diff --check`.

## Documentation Output

After successful verification:

- Create `docs/dynamic-multicast-port-qa-fix-implementation-summary.md` with the changed file, root cause, exact commands, and results.
- Update `.agent-context.md` to state that the runtime packaging blocker is fixed and QA rerun is required.
- Update backlog item 13 to `Implemented - Ready For QA Rerun`.
- Do not rewrite the original QA report; it is historical evidence of the failed cycle.

## Acceptance Criteria

- `requirements.txt` declares `greenlet==3.0.3`.
- The clean runtime import succeeds without installing `requirements-test.txt`.
- The full suite passes with the packaging guard included.
- The rebuilt API remains running and all four smoke endpoints respond successfully.
- Production Compose rendering and frontend syntax checks remain clean.
- The implementation summary and project context identify the fix and return the task to QA.

## Consultation Decision

No Architect or Product Lead consultation is required for the requested fix.

- Architect review is unnecessary because worker networking, control-plane topology, schemas, and runtime behavior are unchanged.
- Product Lead review is unnecessary because there is no user-visible scope or workflow change.

Escalate to the Architect only if the Implementer proposes changing the base image, Python version, dependency-management strategy, SQLAlchemy major version, or Docker build model. Escalate to the Product Lead only if remediation changes supported deployment behavior or delays/removes an accepted user capability.

## Next Step

Implement the dependency repair and verification exactly as scoped, then hand the evidence back to Dev Lead for a short review before QA rerun.

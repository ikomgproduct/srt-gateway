# Dynamic UDP Multicast Intake - Dev Lead To QA Handoff

## Verdict

Dev Lead review is complete and the implementation is approved to enter QA.

The automated regression and configuration checks are passing. Release approval still requires browser/API validation and physical multicast testing on production-like Linux hardware.

## Goal

Validate that an operator can configure and run UDP multicast sources on any administrator-approved port in the default `1024-65535` range without broad Docker UDP port publication, while preserving route compatibility, HA behavior, and network-zone isolation.

## Required Reading

- `.agent-context.md`
- `backlog/tasks.md`, item 13
- `docs/dynamic-multicast-port-dev-lead-implementer-instructions.md`
- `docs/dynamic-multicast-port-implementation-summary.md`
- `README.md`
- `UI_USER_GUIDE.md`

## QA Preconditions

- Run hardware QA on Linux with the production NIC layout or an equivalent lab topology.
- Configure Main Video, Backup Video, DMZ Video, and Management entries in `INTERFACE_INVENTORY_JSON`.
- Confirm the worker hosts own every configured video IP.
- Confirm switch/router IGMP behavior and host firewall rules permit the selected multicast groups and UDP ports.
- Use unique, policy-compliant test groups and ports that do not carry live traffic.
- Use an authenticated `REDIS_URL` and `WORKER_REDIS_URL`, a non-empty `REDIS_PASSWORD`, and the intended `REDIS_BIND_IP`/`REDIS_PORT`.
- Set `UDP_MULTICAST_PORT_MIN` and `UDP_MULTICAST_PORT_MAX`; the default expected policy is `1024-65535`.
- Start the canonical production Compose file directly. `docker-compose.production.video-zones.yml` is compatibility-only and intentionally has no effective services.

Site reference topology:

| Zone | NIC | Reference IP | Purpose |
| --- | --- | --- | --- |
| Main Video | `eno1` | `10.70.15.3` | Internal main video input/output |
| Backup Video | `eno2` | `10.71.15.3` | Internal backup video input/output |
| DMZ Video | `eno3` | `10.75.51.40` | External video input/output |
| Management | `eno4` | `10.75.15.3` | Internal control-plane traffic only |

## Automated Checks

Rerun the full suite using the established container workflow:

```powershell
docker compose -f docker-compose-microservices.yml run --rm --no-deps api sh -c "pip install -q pytest pytest-asyncio aiosqlite httpx==0.24.1 greenlet && python -m pytest -q"
```

Expected baseline: `122 passed`.

Also verify:

1. `node --check frontend/app.js` passes.
2. `docker compose config` renders successfully with each production example: single-server, control-plane, primary worker, and backup worker.
3. Single-server Compose also renders when the no-op compatibility override is included.
4. `git diff --check` reports no whitespace errors. Existing CRLF conversion warnings are not failures.

## API And Browser Scenarios

1. Confirm `GET /api/runtime-policy` returns the configured multicast minimum and maximum ports.
2. Select UDP Multicast in create and edit flows. Confirm the port field uses the runtime policy bounds.
3. Switch to UDP Unicast and other protocols. Confirm their port controls return to the normal `1-65535` behavior.
4. Confirm interface dropdowns show Main Video, Backup Video, and DMZ Video where permitted, and never offer Management for media binding.
5. Create and edit both structured routes and legacy flat-field routes. Confirm existing values hydrate correctly and save without losing compatibility fields.
6. Confirm ports `1024` and `65535` are accepted under the default policy and `1023` is rejected.
7. Confirm two enabled/running-intended routes cannot claim the same multicast bind IP and port. Expect HTTP `422` with the conflicting route identified.
8. Confirm disabled templates may overlap, but enabling or explicitly starting a conflicting route is rejected.

## Physical Multicast Matrix

Send a real MPEG-TS multicast source for each case and verify the selected worker receives traffic, FFmpeg remains running, and the configured output or preview advances.

| Zone | Port 1024 | Port 5500 | Port 65535 |
| --- | --- | --- | --- |
| Main Video | Required | Required | Required |
| Backup Video | Required | Required | Required |
| DMZ Video | Required | Required | Required |

For each result, record the multicast group, source host/interface, receiving worker, route ID, sender command, relevant worker log lines, and proof of output activity. Do not include passwords or Redis URLs containing credentials.

## HA And Recovery Scenarios

1. With an all/active-active target, confirm primary and backup workers can join the same group and port through their resolved bindings.
2. With active-passive behavior, confirm only the lease owner starts FFmpeg.
3. Restart each worker and confirm desired state is reconciled and the multicast group is rejoined.
4. Confirm reconciliation recovers desired state after a missed Pub/Sub event.
5. Change the route binding, group, or port after a stable failure and confirm the configuration fingerprint changes and the route is attempted again.
6. Use explicit start/retry after correcting a stable failure and confirm the route can recover without recreating it.

## Failure Classification And Restart Control

Validate each failure through the API state, worker logs, and metrics where available:

| Scenario | Expected code | Retryable | Expected behavior |
| --- | --- | --- | --- |
| Bind IP absent on worker host | `invalid_bind_interface` | No | Stable failure; no restart loop |
| Port outside runtime policy | `port_out_of_policy` or API `422` | No | Route does not start |
| Local bind/port occupied | `port_in_use` | No | Recognized FFmpeg stderr is retained |
| Multicast group join fails | `multicast_join_failed` | No | Recognized FFmpeg stderr is retained |
| Unclassified transient FFmpeg exit | Generic runtime error | Yes | Existing retry behavior remains |

Observe each non-retryable case for at least 30-45 seconds. There must be no repeated watchdog recovery or FFmpeg restart storm. After correcting the configuration, use explicit start/retry and confirm recovery.

## Deployment And Security Checks

1. Confirm production workers use host networking and have no worker `ports:` publication.
2. Confirm Redis authentication is enforced.
3. In single-server deployment, confirm Redis is bound only to loopback.
4. In multi-server HA, confirm Redis is bound only to the Management network and is reachable by remote workers through that network.
5. Confirm Redis and Postgres are not reachable through the DMZ interface.
6. Confirm API/UI and Grafana remain reachable through their configured operational endpoints.
7. Confirm the old two-file Compose command still renders but the compatibility override does not alter the canonical production model.

## Regression Coverage

Exercise at least one existing route for each available non-multicast path so this change does not regress SRT listener/caller, UDP unicast, RTMP/RTMPS, RIST, HLS input/output, destination fan-out, UI create/edit hydration, or HA lease behavior.

## Evidence And Reporting

The QA report must include:

- Active project and tested commit SHA.
- Redacted environment and rendered Compose validation.
- Automated commands and exact results.
- Browser/API scenarios with Pass, Fail, or Blocked status.
- The completed nine-case physical multicast matrix.
- HA/recovery and failure-classification evidence.
- Relevant `docker compose ps`, API responses, sender commands, worker logs, and network observations.
- Exact reproduction steps for every failure.
- A final release verdict: Pass, Fail, or Blocked.

## Release Gate

QA may approve the release only when:

- all automated checks pass;
- all required physical multicast cases pass or an explicitly approved reduced matrix is documented;
- HA ownership, restart, reconciliation, and explicit recovery pass;
- stable failures do not create restart storms;
- Management is not offered as a media interface;
- Redis/Postgres are not exposed through DMZ; and
- no critical regression is found in existing protocols or route editing.

Current state: **Ready For QA**. Dev Lead did not execute the physical hardware scenarios.

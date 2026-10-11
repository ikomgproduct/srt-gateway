# Dynamic UDP Multicast Intake - Reviewer-Fix QA Report

Date: 2026-10-11
Tested branch/commit: `main` / `7b5b8cd` plus the current uncommitted implementation changes

## Result

**Blocked for final release approval - software QA passed; physical-site release gates remain.**

No software blocker was found in the reviewer-fix release. The full automated
suite, production Compose matrix, clean image packaging, live PostgreSQL and
Redis lifecycle, concurrent admission behavior, and browser create workflow
passed.

Final approval still requires the physical Linux multicast matrix, two-worker
HA/rejoin and reconciliation tests, DMZ network-isolation checks, and a normal
supported-browser edit workflow on the target deployment.

## Automated And Packaging Results

| Check | Result | Evidence |
| --- | --- | --- |
| Full regression suite | Pass | `148 passed in 1.90s` |
| Frontend JavaScript syntax | Pass | `node --check frontend/app.js` |
| Production Compose matrix | Pass | Single-server, control-plane, primary, backup, and compatibility override |
| Missing Grafana password guard | Pass | Compose failed with the expected required-variable error |
| Clean API image build | Pass | API image rebuilt with `--no-cache` |
| Clean runtime imports | Pass | `greenlet`, SQLAlchemy asyncio, and `api.main` imported from the rebuilt image |
| Whitespace validation | Pass | `git diff --check`; line-ending conversion warnings only |

## Live End-To-End Results

- API, PostgreSQL, Redis, worker, telemetry, Prometheus, and Grafana started and
  remained running.
- `/`, `/api/runtime-policy`, `/api/interfaces`, `/api/workers`, and Grafana
  returned successful responses.
- Runtime multicast policy reported `1024-65535`.
- Two disabled templates with the same multicast claim were accepted. Starting
  the first succeeded; starting the second returned HTTP `422` with the
  conflicting route identified.
- An exact Management interface identity was rejected as ineligible for media
  input.
- The enabled route reached a stable `invalid_bind_interface` failure because
  the Windows lab worker does not own `10.70.15.3`. It did not enter a watchdog
  restart loop.
- PostgreSQL persisted the expected enabled/disabled state, and Redis
  `service_configs` matched committed desired state. Stop/delete removed the
  records from both stores.
- Two simultaneous HTTP creates against PostgreSQL for the same bind claim
  produced exactly one HTTP `200` and one HTTP `422`. Only one record was
  committed, directly exercising the PostgreSQL advisory-lock path.
- All QA-created service records were removed after verification.

## Browser Results

| Scenario | Result | Notes |
| --- | --- | --- |
| Dashboard and assets | Pass | UI, CSS, JavaScript, inventory, policy, and service data loaded |
| Protocol-aware source controls | Pass | UDP selection hid SRT fields and exposed Unicast/Multicast, TTL, and MTU |
| Protocol-aware destination controls | Partial | UDP selection exposed UDP controls and hid SRT mode, latency, passphrase, and redundancy; post-QA review found that destination Stream ID subfields remain visible |
| Interface filtering | Pass | Main Video, Backup Video, and DMZ Video were offered; Management was absent |
| Structured create | Pass | Created multicast source `239.20.20.20:5600` on Main Video and UDP destination on DMZ Video |
| Structured persistence/display | Pass | Dashboard displayed the expected source/destination URLs and pending-worker explanation |
| Edit hydration through browser automation | Blocked | The compact edit icon was visible but could not be reliably activated by the in-app automation target |
| Chrome cross-check | Blocked | No Chrome automation target was available in this environment |

Static/unit coverage for structured and legacy edit hydration passed in the
full regression suite. A normal supported browser must still exercise create,
edit, save, reload, and legacy hydration on the target system.

Post-QA review identified one non-blocking P2 UI issue: destination SRT Stream
ID subfields are not gated by destination protocol and remain visible for UDP
and other non-SRT destinations. Serialization remains protocol-safe. See
`docs/dynamic-multicast-port-post-qa-review.md`.

## Expected Lab Limitations

- The lab worker is `worker_1`, while the browser-created service targeted the
  production `primary` role, so the UI correctly reported `pending_worker`.
- The Windows Docker lab does not own the site video IPs. The observed
  `invalid_bind_interface` worker errors were produced intentionally by
  negative tests and were stable/non-retryable.
- Real multicast, IGMP behavior, Linux host networking, and physical NIC
  isolation cannot be proven in this environment.

## Remaining Release Gates

1. Run MPEG-TS multicast on ports `1024`, `5500`, and `65535` through Main
   Video, Backup Video, and DMZ Video.
2. Validate primary/backup ownership, active-passive behavior, worker restart,
   multicast rejoin, and reconciliation after missed Redis events.
3. Validate occupied-port and multicast-join failure classification for at
   least 30-45 seconds without restart storms, then verify explicit recovery.
4. Prove Redis and PostgreSQL are unreachable from DMZ while API/UI and Grafana
   remain reachable through the approved VPN/firewall path.
5. Complete route create/edit/reload and legacy/structured hydration in a
   normal supported browser on the target system.
6. Fix and retest destination SRT Stream ID field visibility for non-SRT
   destination protocols.

## Recommendation

Approve the reviewer fixes for deployment to the production-like QA server.
Do not grant final production release approval until all remaining physical
release gates pass and their evidence is attached to this report or a target-
hardware addendum.

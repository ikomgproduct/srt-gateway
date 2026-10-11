# Dynamic UDP Multicast Intake - Post-QA Reviewer Report

Date: 2026-10-11
Active project: `C:\worklocal\ikoSRTgateway`

## Verdict

**Approved for production-like Linux hardware QA. Not approved for final
production release.**

The previous reviewer findings are resolved. Independent review confirmed the
deterministic `all` role validation, exact interface identity checks,
disabled-template validation, transaction-safe PostgreSQL admission, post-
commit Redis synchronization, mandatory production Grafana password, and the
host-network worker deployment model.

Independent verification completed with `148 passed in 2.32s`, successful
frontend syntax validation, and a clean whitespace check. The temporary test
container and network were removed after review.

## Finding

### P2 - Destination SRT Stream ID fields remain visible for non-SRT protocols

`frontend/app.js` toggles `.destination-stream-default-field` and
`.destination-stream-custom-field` only from the Stream ID mode. It does not
also require `destinationProtocol === "srt"`.

As a result, UDP destinations correctly hide SRT mode, latency, passphrase, and
path-redundancy controls, but can still display SRT-only Host Mode, Resource
Name, Username, or Custom Destination Stream ID controls. Serialization is not
affected because structured SRT parameters are emitted only for SRT
destinations.

Recommendation:

- Gate both destination Stream ID field groups on normal destination enabled,
  destination protocol SRT, and the selected Stream ID mode.
- Add a frontend regression test that verifies the complete visible field set
  for UDP and at least one other non-SRT destination protocol.

This P2 does not block multicast, HA, recovery, or network-isolation testing on
production-like hardware. It should be fixed and retested before final release.

## Hardware-QA Preconditions

- Use isolated test multicast groups and ports that do not carry live traffic.
- Replace every committed `change-me` placeholder with site QA credentials.
- Confirm each worker host owns every configured video-interface IP.
- Confirm host firewall and switch/router IGMP policy allow the test matrix.
- Keep Redis and PostgreSQL unavailable from DMZ; expose them only through the
  approved loopback or Management path.
- Treat this as production-like QA approval, not permission for live production
  traffic or final release.

## Remaining Release Gates

- Physical nine-case Main Video, Backup Video, and DMZ multicast matrix.
- Primary/backup ownership, restart, rejoin, and reconciliation behavior.
- Stable occupied-port, invalid-interface, and multicast-join failures without
  restart storms, followed by explicit recovery.
- Redis/PostgreSQL DMZ-isolation verification.
- Normal supported-browser create, edit, save, reload, and legacy/structured
  hydration validation.
- Resolution and retest of the P2 destination Stream ID visibility finding.

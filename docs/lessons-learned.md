# Lessons Learned

Project-specific lessons for this project.

Use this file for facts, decisions, gotchas, and repeatable checks that are specific to this project. Promote only reusable team practices to `C:\worklocal\ikodevteam\.agents\memory` after approval.

## Current Lessons

### 2026-09-02 - Production compose is the HA contract

Lesson:

Use `docker-compose.production.yml` as the canonical production deployment file for both single-server HA and multi-server HA. Keep `docker-compose-microservices.yml` and the other older compose files as lab/legacy paths, and do not overwrite server-local compose edits without explicit approval.

Why it matters:

The production server may carry local environment-specific changes. A separate production compose contract lets the team support one-server and multi-server hardware layouts without damaging lab or server-local files.

Applies to:

Production deployment, release notes, server update instructions, and future compose changes.

Promote to shared memory: No

### 2026-09-02 - Interface inventory and runtime networking are separate layers

Lesson:

`INTERFACE_INVENTORY_JSON` controls what the API/UI exposes as selectable route interfaces. Production host-network workers bind those host IPs directly, while `UDP_MULTICAST_PORT_MIN/MAX`, the host firewall, and the physical network control which service ports are permitted and reachable.

Why it matters:

The values must describe the same physical NIC plan, but changing UI inventory does not configure host NICs, firewall rules, routing, or IGMP behavior.

Applies to:

Network-zone changes, deployment support, route editor troubleshooting, and production env reviews.

Promote to shared memory: No

### 2026-09-02 - Network zones must stay distinct in docs and UI

Lesson:

The accepted site model is Main Video `10.70.15.3`, Backup Video `10.71.15.3`, DMZ Video `10.75.51.40`, and Management `10.75.15.3`. Management must not appear as a media route endpoint. Current production examples directly expose API/UI on the DMZ-facing address and Grafana on both Management and DMZ-facing addresses, while Redis/Postgres stay Docker-internal or management-network-only.

Why it matters:

Earlier wording blurred DMZ and Management addresses, which made deployment and operator guidance confusing. Docs should say whether an address is media, operator-facing DMZ, or internal management/control-plane.

Applies to:

Product brief, architecture docs, README, UI guide, env examples, and support answers.

Promote to shared memory: No

### 2026-09-02 - Route endpoint selections must preserve interface identity, not only IP

Lesson:

Route endpoint dropdowns need to preserve `interface_id` separately from `bind_ip`. Some lab or HA layouts can reuse the same IP across multiple selectable zones or roles, so using IP as the only select value can hydrate or save the wrong zone.

Why it matters:

Duplicate/shared-IP layouts are explicitly supported for lab compatibility and flexible hardware configurations. Stable interface identity keeps edit hydration, path redundancy defaults, and payload serialization predictable.

Applies to:

Route Editor V2 UI, `/api/interfaces`, structured `source` / `destinations` payloads, and future browser tests.

Promote to shared memory: No

### 2026-09-02 - Prometheus is internal in production compose by default

Lesson:

Production compose does not publish Prometheus directly on a host port. Operator-facing monitoring should point to Grafana unless production compose is intentionally changed to expose Prometheus.

Why it matters:

The UI guide previously advertised a direct Prometheus URL that production compose did not provide. Keeping this accurate avoids false troubleshooting steps during server deployment.

Applies to:

README, UI guide, monitoring docs, and support runbooks.

Promote to shared memory: No

### 2026-09-02 - Browser automation for Route Editor V2 remains a planned test gap

Lesson:

Route Editor V2 currently has static frontend tests and backend regression coverage, but no committed browser automation harness. Duplicate-IP interface selection and protocol-aware field visibility still need real DOM/browser coverage in a future test slice.

Why it matters:

Static tests caught important source-code expectations, but they cannot fully prove operator-visible create/edit behavior. This should be addressed before the route editor grows further.

Applies to:

QA planning, Route Editor V2 releases, and future Playwright setup.

Promote to shared memory: No

### 2026-10-06 - Per-service UDP ports and Docker-published ranges are different contracts

Lesson:

The Route Editor can store any valid UDP source port, but a container can receive that traffic only when its deployment network makes that port reachable. The current production Compose window `9000-9010` therefore limits runtime reachability even though API validation permits a wider range.

Why it matters:

UI/API acceptance must not be mistaken for deployable multicast support. The selected source port, worker network mode, host/interface reachability, and FFmpeg socket behavior must agree.

Applies to:

UDP multicast intake, worker networking, Compose validation, runtime startup checks, and QA.

Promote to shared memory: No

### 2026-10-06 - Full UDP-range publication is not the target multicast design

Lesson:

Do not publish `1024-65535/udp` through Docker bridge/NAT on shared production IPs as the default solution. API/Grafana are TCP services and are not direct UDP socket conflicts, but the publication still reserves nearly the entire UDP namespace, overlaps ephemeral UDP ports, creates a large NAT/firewall footprint, and does not prove correct multicast/IGMP behavior. Use host-network workers so each FFmpeg process binds only its selected port.

Why it matters:

The gateway must support arbitrary operator-selected multicast ports without reserving nearly the entire host UDP namespace or weakening management-plane isolation.

Applies to:

Single-server HA, multi-server HA, Main/Backup/DMZ media networking, and production deployment design.

Promote to shared memory: Yes

### 2026-10-11 - Derived bind claims require transaction-scoped admission

Lesson:

When a uniqueness rule is derived from normalized JSON, role fallback, and enabled state, checking for conflicts before a later commit is race-prone. Serialize the authoritative conflict query and commit in one transaction-scoped admission guard; use PostgreSQL advisory locking across API replicas and a local async lock for same-process and SQLite behavior.

Why it matters:

Two concurrent route mutations could otherwise both observe an available multicast bind and commit duplicate enabled claims. Redis synchronization must remain after the committed database state.

Applies to:

Enabled multicast create, update, and start operations in the SRT Gateway control plane.

Promote to shared memory: No

### 2026-10-11 - Protocol-aware forms need complete visible-field assertions

Lesson:

Route Editor protocol switching must validate the complete visible field set,
not only the primary mode and transport controls. UDP destination selection hid
the main SRT controls but left nested SRT Stream ID fields visible because they
were governed only by Stream ID mode.

Why it matters:

Serialization can remain correct while the operator UI still presents invalid
or confusing fields. Static presence tests and partial browser checks can both
miss nested visibility rules.

Applies to:

Route Editor V2 protocol switching, browser regression tests, QA reports, and
future protocol-specific form additions.

Promote to shared memory: Yes - promoted to shared QA and review memory on 2026-10-11

## Candidate Shared Lessons

### 2026-10-06 - Host-network workers need separate control-plane connectivity

Lesson:

Moving production media workers to host networking removes Compose service-name connectivity for those workers. Keep bridge clients on the internal Redis URL and give host-network workers a separately authenticated loopback or Management URL.

Why it matters:

The media-plane network change and Redis authentication must be deployed atomically. Mixing old URLs, unauthenticated clients, and the new Redis command causes workers or the API to restart even when Compose renders successfully.

Applies to:

Production single-server and multi-server worker deployment, upgrade, and rollback.

Promote to shared memory: No

### 2026-10-06 - Stable network configuration failures need fingerprinted retry suppression

Lesson:

Invalid interfaces, policy-rejected ports, occupied sockets, and multicast join failures should remain visible without being restarted forever. Suppress automatic retry while the normalized configuration fingerprint is unchanged, while allowing a configuration edit or one explicit operator retry.

Why it matters:

This prevents watchdog restart storms while preserving recovery from operator corrections and transient unknown failures.

Applies to:

Worker reconciliation, watchdog behavior, metrics, and operator diagnostics.

Promote to shared memory: No

Use this section for lessons that may be useful across projects. Approved lessons may also be recorded in shared team memory.

### 2026-10-07 - Test-container package installation can hide broken runtime images

Lesson:

Running `pip install` for test dependencies inside an ephemeral test container can make imports succeed even when the production runtime dependency file is incomplete. Always boot a freshly built application image as part of release QA, in addition to running the unit suite.

Why it matters:

The multicast regression suite passed after test dependencies were installed, while the clean API image immediately entered a restart loop because SQLAlchemy asyncio could not import `greenlet`.

Applies to:

Docker image packaging, dependency changes, release QA, and any test workflow that installs extra packages after image build.

Promote to shared memory: Yes

## Template

```md
### YYYY-MM-DD - Lesson title

Lesson:

Why it matters:

Applies to:

Promote to shared memory: Yes / No
```

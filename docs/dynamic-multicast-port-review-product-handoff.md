# Dynamic UDP Multicast Intake - Reviewer Follow-Up Product Handoff

## Goal

Resolve the final Reviewer findings for dynamic UDP multicast intake before returning the release to QA and target-hardware validation.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Current State

- Linux host networking remains the approved production worker model.
- The runtime dependency repair is complete.
- Local QA passed the no-cache runtime build, live API checks, all production Compose renders, frontend syntax validation, and the full `129 passed` regression.
- Final hardware and normal-browser QA remain pending.
- Reviewer requested changes for multicast validation, concurrent conflict admission, deployment documentation, and DMZ control-plane security.

## Product Decisions

### Private DMZ Security Boundary

- The site DMZ is not connected directly to the public network.
- Operator access requires VPN connectivity.
- Lack of application-level authentication is therefore not a P1 blocker for this release, provided deployment firewall rules restrict API/UI and Grafana access to approved VPN users.
- The VPN-only/private-DMZ assumption and required firewall restriction must be explicit production prerequisites.
- `GRAFANA_ADMIN_PASSWORD` must be mandatory in production; the canonical production Compose file must not silently fall back to `admin`.
- An authenticated HTTPS reverse proxy or application authentication remains future defense-in-depth work and is not added to this multicast repair scope.

### `target_node: all`

- A multicast service targeting `all` must validate both primary and backup execution paths.
- An incomplete binding map must not cause the API to validate one role while the other worker later attempts an unvalidated fallback.
- Production behavior should reject an enabled/start request when either required role has no valid media binding.
- Legacy configuration may remain readable/editable, but it must not bypass enabled/start validation.

### Interface Identity

- When `source.primary_endpoint.interface_id` is supplied, validation must resolve that exact inventory entry.
- The selected inventory entry must be `purpose: video`, permit the `input` direction, and allow the worker role being validated.
- Its configured IP must match the submitted `bind_ip`.
- Management must remain invalid for media even when it shares an IP with an eligible video inventory entry.
- IP-only fallback may remain for legacy payloads without `interface_id`, subject to existing compatibility rules.

### Disabled Templates

- Disabled multicast templates may overlap another service's bind claim.
- Disabled templates must still have a valid IPv4 multicast group, policy-approved port, and eligible media interface.
- Only the database bind-conflict scan is deferred until create/update/start becomes running-intended.

### Concurrent Conflict Admission

- Two simultaneous create, update, or start requests must not both claim the same protected `(bind_ip, source_port)` key.
- Architect should select a transaction-safe mechanism compatible with PostgreSQL and the project's SQLite test path.
- The solution must preserve the current first-release rule that different enabled service IDs cannot share one resolved bind IP and source port.

### Documentation

- Remove current-production guidance that refers to retired `PRIMARY_VIDEO_IP`, `BACKUP_VIDEO_IP`, fixed worker port windows, or required Docker UDP publication.
- Clearly distinguish the former bridge limitation from the current host-network production model.
- Keep the one-release no-op `docker-compose.production.video-zones.yml` compatibility note.
- Replace stale test-result summaries with the latest QA state or point readers to the current QA report.

## Acceptance Criteria

- Enabled and start validation covers primary and backup for `target_node: all`.
- A missing or invalid role binding returns an actionable HTTP `422` before Redis synchronization or worker launch.
- Interface validation uses exact identity when supplied and rejects Management in duplicate-IP inventories.
- Disabled services reject invalid multicast addresses, out-of-policy ports, and ineligible interfaces while still allowing bind overlap.
- Concurrent conflicting operations cannot both commit an enabled claim.
- Production Compose requires an explicit Grafana administrator password.
- Production documentation states that API/UI and Grafana access is private-DMZ, VPN-only, and firewall-restricted.
- README, UI guide, architecture, product brief, and project context contain no contradictory current-production port-publication guidance.
- Existing flat compatibility payloads, valid structured routes, non-multicast protocols, worker retry suppression, and Redis synchronization remain covered.
- Full automated regression, no-cache runtime startup, all production Compose renders, and frontend syntax checks pass.

## Required Tests

- `target_node: all` with only primary binding and only backup binding.
- Valid primary/backup bindings for `target_node: all`.
- Duplicate-IP inventory containing both Management and Video interface IDs.
- `interface_id` and `bind_ip` mismatch.
- Disabled multicast templates with invalid group, invalid port, and Management binding.
- Disabled overlapping templates followed by enable/start conflict rejection.
- Concurrent conflicting create requests and, where practical, update/start requests.
- Production Compose fails clearly when `GRAFANA_ADMIN_PASSWORD` is missing.
- Static documentation regression checks for removed port-publication guidance.

## Out Of Scope

- Full application authentication/authorization.
- VPN provisioning or firewall administration from the product.
- HTTPS proxy implementation.
- Automatic failback.
- SRT Rendezvous.
- Linux Netplan editing.
- Changing the approved host-network worker architecture.

## Architect Output

Architect should:

1. Define the corrected validation and role-resolution contract.
2. Select the concurrency-control mechanism and explain database/test implications.
3. Define production Compose and documentation corrections for the private VPN-only DMZ assumption.
4. Identify exact implementation files and compatibility risks.
5. Prepare a scoped Dev Lead handoff with ordered implementation and verification steps.

No product question currently blocks architecture planning.

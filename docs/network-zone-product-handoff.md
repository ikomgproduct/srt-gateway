# Network Zone Product Handoff

## Goal

Prepare the next architecture step for SRT Gateway network separation across video, DMZ, and management networks.

## Active Project

`C:\worklocal\ikoSRTgateway`

## Site Network Model

The target site model separates video and control-plane traffic by network zone:

- Main Video: `eno1`, `10.70.15.3`, internal video input/output.
- Backup Video: `eno2`, `10.71.15.3`, internal video input/output.
- DMZ Video: `eno3`, `10.75.51.40`, public/external video input/output.
- Management: `eno4`, `10.75.15.3`, API, SSH, Grafana/admin, and internal control-plane communication.

This structure should be treated as the standard network architecture pattern, even when individual lab or deployment hosts use fewer NICs or shared IPs.

## Confirmed Product Decisions

- DMZ Video must be selectable for both input and output on both primary and backup workers.
- DMZ Video supports redundant-stream cases where only one external/public network is available for publishing.
- Main Video and Backup Video are paired internal redundant paths.
- If Main Video is selected as the primary internal path, the paired redundant path should use Backup Video.
- If Backup Video is selected as the primary internal path, the paired redundant path should use Main Video.
- API/internal service communication should use the Management network.
- Operator access to the UI and Grafana will still come through DMZ.
- The architecture must explicitly decide whether UI/Grafana bind directly to DMZ-facing IPs or are exposed through a DMZ reverse proxy that forwards to management-bound services.
- Interface choices should be grouped in the UI for now as Main Video, Backup Video, and DMZ Video.
- Worker UDP publish IPs and port ranges must be configurable in env files.

## Product Requirements For Architect

- Define a zone-aware interface inventory model.
- Keep Management out of media source/destination dropdowns.
- Allow DMZ Video in both source and destination dropdowns.
- Define paired internal path behavior for Main Video and Backup Video.
- Define whether paired path selection is automatic, operator-editable, or both.
- Define env-driven production compose behavior for multiple video bind IPs.
- Cover single-server HA and multi-server HA.
- Preserve lab compatibility where fewer NICs or shared IPs are used.
- Preserve current Route Editor V2 structured contract compatibility.
- Keep `docker-compose.production.yml` as the canonical production HA compose file.

## Acceptance Criteria For Architect Plan

- The plan separates worker role, network zone, and route direction.
- The interface inventory schema can represent NIC name, IP, zone, purpose, allowed directions, and worker role eligibility.
- Route input/output dropdown filtering is based on video purpose and input/output direction, not only worker role.
- Management interfaces cannot be selected as media route endpoints.
- DMZ Video can be selected for source and destination paths.
- Internal Main/Backup path pairing is clearly specified.
- Production compose/env strategy supports configurable worker UDP ports on the required video IPs.
- Security implications of DMZ UI/Grafana exposure are called out.
- Multi-server HA implications for Redis/Postgres management access and shared preview/HLS storage remain documented.

## Out Of Scope

- Linux Netplan or NIC IP editing.
- Automatic failback.
- SRT Rendezvous.
- Authentication/authorization redesign.
- Redis/Postgres HA redesign beyond deployment guidance needed for the network-zone plan.

## Suggested Next Step

Architect should prepare a technical plan and Dev Lead handoff for a new backlog item covering network-zone interface inventory, UI filtering, and production compose/env changes.

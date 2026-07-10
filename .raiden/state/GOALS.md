# Goals

## Primary Goal

Ship Arborist, an MCP server that lets Claude (or any MCP client) query a
self-hosted Scanopy network-topology instance and curate the human-owned
overlay (names, descriptions, tags, bindings) without ever writing to what
Scanopy's scanner discovered.

## Milestones

| # | Milestone | Status |
|---|---|---|
| 1 | RAIDEN Orientation | Done |
| 2 | Core client, version guard, dual transport (stdio/http) | Done |
| 3 | Read-only tool profile (14 tools) | Done |
| 4 | Read-write curated-overlay tool profile (11 tools) | Done |
| 5 | Network-scope confinement (hosts, services, subnets, bindings) | Done |
| 6 | Org-scoped resource (tag) confinement audit | Done — F5 scope-confinement pass, 2026-07-07 |
| 7 | Deployment targets (Docker, Podman Quadlet, Proxmox LXC) | Done |
| 8 | GitHub remote + publish (`OWNER` placeholder fill-in) | Done — 2026-07-09 (LOOP-001) |
| 9 | Cut `v0.1.0` tag per RELEASE.md | Done — 2026-07-09 (LOOP-001) |

## Out of Scope (current)

- Writing to Scanopy's discovered layer (hostnames, IPs, MACs, ports,
  interfaces) — permanent, by design, not a milestone to relax later.
- Multi-network federation in a single Arborist process.

## Provenance

RAIDEN Instance installed 2026-07-08. Goals captured from
README.md, CHANGELOG.md, and RELEASE.md at install time.

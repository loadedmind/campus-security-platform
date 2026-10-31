# ADR-0001: A site is a data file; per-site state

**Status:** accepted

## Context
The platform must scale by number of campuses without growing the code or the team. Onboarding has historically been a multi-week project of hand-built servers.

## Decision
- Each site is `sites/<name>.yaml`, validated against `sites/_schema.json` and cross-file rules (`scripts/validate_sites.py`).
- One Terraform stack, invoked once per site with its own state file (`tfstate/<site>.tfstate`).
- Terraform outputs are the single source for both the Ansible inventory and Prometheus targets.
- Images, releases and patch rings are pinned in the site file, so a site's full desired state is reviewable in one diff.

## Consequences
- Blast radius of an apply is one site. A bad module change is caught at the canary before it reaches others (core first, then campuses one at a time).
- Deleting a site file never destroys anything by itself; `teardown` is explicit.
- Cross-site changes (module, role) fan out to every site via the deploy matrix, serialized.

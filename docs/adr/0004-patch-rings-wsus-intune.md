# ADR-0004: Patch rings (WSUS in the lab, Intune/WUfB in production)

**Status:** accepted for the lab

## Context
Security endpoints (VMS servers, access-control head ends) must be patched monthly without a person on each host, and a bad cumulative update must not reach every campus.

## Decision
- Rings are WSUS computer target groups (`ring0`, `ring1`, `ring2`) assigned by client-side targeting from the site's `patch_ring` (DSC registry policy). Hosts never auto-install (`NoAutoUpdate=1`).
- `patch` runs the Wednesday after Patch Tuesday:
  1. **Ring 0** approves needed, non-superseded Critical/Security updates and records the exact update IDs.
  2. Every ring: pre-health check, Hyper-V checkpoint of each VM, install in 50 % batches with reboots, then a 15-minute clean health gate in Prometheus.
  3. **Ring 1/2** approve **only** the recorded set after the environment wait timer (soak).
  4. Gate failure -> restore that ring's checkpoints automatically, halt; later rings never start.

## Mapping to Intune / Windows Update for Business

| Lab step | Intune / Graph equivalent |
|---|---|
| WSUS target group per ring | Update ring or Autopatch group per ring (Entra ID device groups) |
| Ring 0 approval + recorded IDs | Expedited/quality update profile for ring 0; content approval via WUfB deployment service |
| Soak via environment wait timer | Deferral days per ring, or pipeline-held approvals via Graph |
| Prometheus health gate | Same gate, then `pause` the ring via Graph on failure |
| Checkpoint restore | Not available for physical endpoints; rely on uninstall of the quality update or reimage |

## Consequences
- WSUS is deprecated by Microsoft (announced September 2024; still shipped and supported, no new features). The ring/gate/promotion logic is product-independent and moves to Graph calls without changing the workflow shape.
- Initial WSUS synchronization of all products takes hours; narrow `Products` after the first sync.
- WSUS over HTTP 8530 in the lab; production uses HTTPS 8531.

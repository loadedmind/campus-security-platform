# Runbook: release, promote, roll back

## Release
1. Merge changes to `simulator/` or `packages/` with green CI.
2. Tag on main: `git tag v1.3.0 && git push origin v1.3.0`.
3. `release` publishes `campus-sec-sim.1.3.0.nupkg`, `campus-windows-exporter.<upstream>.nupkg` and `SHA256SUMS`.

## Promote
1. PR: bump `platform.release` in `sites/hou-01.yaml` (canary) only. Merge; watch `deploy`.
2. After a soak, one PR bumping the remaining campuses. They deploy one at a time.

## Roll back
- **Automatic:** a failed configure/smoke step re-converges the site to its last known-good release and marks the run failed. The Grafana release table shows the actual running release.
- **Manual:** revert the promotion commit. `deploy` converges to the previous pin (`state: downgrade`).
- **Infrastructure:** revert the commit (e.g. `image:` bump) and approve the plan; VMs are rebuilt from the previous image.

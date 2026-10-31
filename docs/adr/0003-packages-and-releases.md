# ADR-0003: Internal packages, pinned releases, automatic rollback

**Status:** accepted

## Context
Hosts must stay current without anyone logging in, and a bad build must be reversible in minutes.

## Decision
- Everything installed by the platform is a Chocolatey package built by `release` from a semver tag. Third-party binaries are **internalized**: downloaded once in CI, verified against a pinned SHA-256 (`packages/upstream.json`), and embedded.
- Hosts never reach a public feed: the community source is removed in the image; the only source is a folder feed populated from the pinned GitHub Release after checksum verification on both the control node and the host.
- Each site pins `platform.release`. Promotion = PR bumping the pin, canary site first.
- Packages are installed with `state: downgrade` + exact version, so the same task converges up **or** down.
- `deploy` records the last known-good release per site. If configuration or the Prometheus smoke test fails, it re-converges the site to that release and still fails the run (the pinned release is not what is running).

## Consequences
- Rollback needs no new build; the previous release is already in GitHub Releases and usually in the control-node cache.
- Infrastructure changes are not auto-rolled-back (destroying/recreating VMs automatically is riskier than stopping); revert the commit and redeploy.
- At fleet scale the folder feed should become an HTTP NuGet repository; the change is isolated to `roles/chocolatey_client`.

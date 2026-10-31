# Runbook: onboard a campus

Expected effort: one PR, one approval click.

1. Copy an existing campus file: `cp sites/hou-02.yaml sites/<code>-<nn>.yaml`.
2. Edit `name` (must equal the file name), `display_name`, host `name`s (unique, ≤15 chars), `patch_ring` (new campuses start in ring 1 or 2, never 0), `platform.release` (current release on other campuses), `platform.devices`.
3. Open a PR. CI validates the schema and cross-site rules.
4. Merge. The `deploy` run scopes to the new site only.
5. Approve the `lab-infra` environment after reading the plan summary on the run page.
6. Watch for: apply -> configure -> smoke test green. The site appears in Grafana "Campus Fleet Overview" with its release and image.

If the smoke test fails on a first deploy there is no last known-good release, so nothing is rolled back: fix forward or run `teardown`.

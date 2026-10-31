# ADR-0005: Bounded, audited auto-remediation

**Status:** accepted

## Context
On-call load grows linearly with campuses unless repeat fixes are automated. Unbounded automation, however, turns one fault into many (restart loops, mass reboots during an upstream outage).

## Decision
- An alert is eligible only if its rule sets `remediation: <key>` and the key is in `remediation/catalog.yaml`. Adding automation is a reviewed PR to the catalog + a playbook + a rule test.
- Alerts that feed remediation are aggregated **per host** (never per device) so a firmware bump or a switch failure produces one run per host, not hundreds.
- The relay enforces label hygiene, per-target cooldown and an hourly cap. Exceeding the cap stops acting and fires `RemediationSuppressed` (critical).
- Execution goes through GitHub Actions (`repository_dispatch`): same runner, same Ansible, logs and step summaries as every other change.
- The workflow re-validates the payload (catalog, live inventory, regexes), passes values only through environment variables and an extra-vars file, and succeeds only when the triggering alert has cleared for 2 minutes.
- Playbooks carry their own guards: site-wide outages are refused (`MassDeviceOutage` also inhibits upstream), firmware converges in 25 % batches and stops on the first failed batch, service restarts refuse when the service is not installed.
- Some alerts are deliberately human-only: `CameraNotRecording` (evidence gap), `CampusSecSimApiDown` while the service runs (likely a defect), `HostDown`.

## Consequences
- Every automated action is visible in Actions history and on the Grafana "automated remediations" panel; that panel is the toil-avoided metric.
- Remediation depends on GitHub availability and the single runner; both failure modes alert.
- The token used by the relay can trigger the workflow; the workflow treats its payload as untrusted.

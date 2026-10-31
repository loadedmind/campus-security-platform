# Architecture

## Goals

1. **A campus is data, not a project.** Everything site-specific is in `sites/<name>.yaml`. Code is shared.
2. **One path to production.** Every change to a site goes through Git, CI and a deploy run. No console changes; DSC reverts them.
3. **Reversible by default.** Releases are pinned per site; images are immutable and versioned; patches are checkpointed.
4. **Automation is bounded.** It acts only from an allowlist, rate-limited, verified by the same signal on-call uses, and escalates when it fails.

## Components

| Component | Runs where | Responsibility |
|---|---|---|
| Golden image (`packer/`) | built on the Hyper-V host | Windows Server 2025 Core, patched, Chocolatey client, pinned DSC modules, first-boot WinRM HTTPS. Published read-only as `ws2025-core-<yyyy.MM>.vhdx`. |
| Site stack (`terraform/stacks/site`) | automation host | VMs as differencing disks off the pinned image. One state file per site. Outputs IPs/roles for everything downstream. |
| Convergence (`ansible/playbooks/site.yml`) | automation host -> hosts over WinRM HTTPS | Hostname, DSC (baseline, firewall, WSUS client policy and ring, WSUS server on core), package feed, exporter, simulator, release marker. |
| DSC (`dsc/CampusNode.ps1`) | each host's LCM | ApplyAndAutoCorrect every 15 minutes. Drift is fixed on the host without a pipeline run. |
| Packages (`packages/`, `release` workflow) | built on GitHub-hosted Windows | Simulator exe wrapped as a service (WinSW) and the windows_exporter MSI, both checksummed. Delivered per host into a local folder feed. |
| Observability (`observability/`) | automation host (compose) | Prometheus (file_sd targets generated from Terraform outputs), Alertmanager (remediation + human routes, inhibitions), Grafana fleet dashboard. |
| Remediation (`remediation/`, `remediate` workflow) | relay on automation host; playbooks via Actions | Alert -> catalog lookup -> cooldown/cap -> `repository_dispatch` -> validated playbook -> verify alert cleared. |

## Data flow: onboarding a campus

1. PR adds `sites/dal-01.yaml`. CI validates schema, unique host names, file/name match.
2. Merge. `deploy` scopes to `dal-01` only.
3. `plan` on the runner; plan summary posted to the run. Infra change -> `lab-infra` environment waits for approval.
4. `apply` builds the VM from the pinned image; first boot enables WinRM HTTPS.
5. Outputs are written; `render_inventory.py` regenerates the Ansible inventory **and** Prometheus targets; firmware rules are regenerated and Prometheus reloads.
6. The pinned release is staged and checksum-verified; Ansible converges the host.
7. Smoke test: host scraped and up for 2 min, simulator up, no critical alerts for 3 min.
8. Release recorded as last known-good for the site.

## Data flow: a device goes offline

1. `campus_sim_device_up == 0` for 5 min on a host -> `DevicesOffline` (aggregated per host, label `remediation=reboot_offline_devices`).
2. Unless `MassDeviceOutage` (>50 % down) inhibits it, Alertmanager sends it to the relay.
3. Relay checks catalog, label hygiene, cooldown (10 min) and cap (2/h), then dispatches.
4. `remediate` re-validates against catalog + live inventory, runs `reboot_offline_devices.yml` on that host only. The playbook itself refuses if the outage looks site-wide.
5. Workflow waits for the alert to clear (stable 2 min). If not: job fails, alert keeps firing to humans. If the cap is hit: `RemediationSuppressed` pages.

## Trade-offs

| Decision | Cost | Production path |
|---|---|---|
| Self-signed WinRM certs, `server_cert_validation: ignore` | MITM on the LAN is possible | Enrol host certs from an internal CA; validate in Ansible and Terraform (`insecure = false`). |
| Shared local Administrator password baked into the image unattend (deleted at first boot) | Anyone with the VHDX can read it until a VM boots; one secret for the fleet | Domain join + gMSA/LAPS; never put credentials in images. |
| Local Terraform state on the automation host | No remote locking, single copy | Remote backend with locking (S3+DynamoDB, azurerm, GCS, or Terraform Cloud) and backups. |
| Single self-hosted runner, also hosting monitoring | Single point of failure for deploys, patching **and** remediation | Runner pool per site group; monitoring on separate hosts; out-of-band alert path. |
| Self-hosted runner on a **public** repo | Untrusted code could reach the lab | Jobs that use the runner trigger only on push to main, tags, dispatch, schedule; never on `pull_request`. Require approval for outside-contributor workflow runs. Prefer a private repo for real environments. |
| Per-host folder feed for Chocolatey | Copies packages to every host; does not scale to hundreds of hosts | HTTP NuGet feed (ProGet, Nexus, Artifactory). Only the `source` changes. |
| `taliesins/hyperv` provider (community, last upstream commit Mar 2024) | Maintenance risk; replacement semantics not fully documented (mitigated with `terraform_data` + `replace_triggered_by`) | In a real estate the target is vSphere, Azure Local or a cloud provider with a maintained provider. |
| WSUS for patch rings | Deprecated by Microsoft (announced Sept 2024), HTTP on 8530 in the lab | Intune / Windows Update for Business deployment rings via Graph; see ADR-0004. |
| WinSW 2.12 as service wrapper | Last stable release is from the v2 line | Native Windows service (pywin32 or a Go/.NET host) built into the app. |
| Remediation routed through GitHub Actions | ~30-90 s added latency; GitHub outage disables auto-remediation (and alerts on it) | Acceptable for these actions; latency-critical actions would run in a local controller with the same catalog. |
| Simulator API over HTTP with bearer token | Token visible on the wire inside the LAN | TLS on the head-end API; vendor SDK with service accounts. |

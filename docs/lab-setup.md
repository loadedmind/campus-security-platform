# Lab setup

Two machines on one LAN:

| Role | Lab machine | Requirements |
|---|---|---|
| Hyper-V host | Windows 11 **Pro/Enterprise/Education** desktop (Home has no Hyper-V), virtualization enabled in firmware, ≥32 GB RAM, ~200 GB free | Runs the VMs only |
| Automation host | Ubuntu Server (24.04+), always on | GitHub Actions runner, Terraform/Ansible control node, observability stack |

Capacity at defaults: core 4 GB + 2 GB per campus VM. Two campuses ≈ 8 GB of guest RAM.

## 1. Hyper-V host (elevated PowerShell)
```powershell
git clone https://github.com/loadedmind/campus-security-platform.git C:\campus-lab\repo
cd C:\campus-lab\repo
.\scripts\bootstrap-hyperv-host.ps1 -AutomationHostIp <automation host IP>   # reboots once to enable Hyper-V; run again after
```
Give the Hyper-V host a DHCP reservation; Terraform addresses it by IP.

## 2. Golden image (Hyper-V host)
1. Download the Windows Server 2025 **evaluation** ISO from the Microsoft Evaluation Center to `C:\campus-lab\iso\ws2025-eval.iso`.
2. Install Packer and `oscdimg` (Windows ADK Deployment Tools).
3. Build:
```powershell
$env:PKR_VAR_admin_password = '<lab admin password, >=14 chars, no < > & " '' >'
.\scripts\build-golden-image.ps1 -IsoPath C:\campus-lab\iso\ws2025-eval.iso -Version 2026.11
```
The VHDX is published read-only to `C:\campus-lab\images\ws2025-core-2026.11.vhdx`. The site files reference it by that name.

## 3. Automation host
```bash
git clone https://github.com/loadedmind/campus-security-platform.git && cd campus-security-platform
sudo ./scripts/bootstrap-automation-host.sh loadedmind/campus-security-platform
```
Then register a repository runner (Settings → Actions → Runners → New self-hosted runner → Linux x64) as user `campus-runner`, with label `campus-lab`, and install it as a service (`sudo ./svc.sh install campus-runner && sudo ./svc.sh start`).

## 4. GitHub configuration
**Secrets:** `LAB_ADMIN_PASSWORD`, `HYPERV_USER` (`campus-automation`), `HYPERV_PASSWORD`, `SIM_API_TOKEN` (≥16 chars).
**Variables:** `HYPERV_HOST` (Hyper-V host IP); optional `CAMPUS_STATE_DIR`, `PROMETHEUS_URL`.
**Environments:** `lab-infra` (required reviewer), `lab-config` (none), `patch-ring0` (none), `patch-ring1` and `patch-ring2` (wait timer = soak, e.g. 1440 min).
**Actions settings:** require approval for workflow runs from all outside collaborators (public repo + self-hosted runner).

## 5. First run
1. Run `observability` (manual dispatch) → Grafana on `http://<automation host>:13000`.
2. Tag `v1.0.0` → `release`.
3. Run `deploy` with site `core`, then `hou-01`, then `hou-02`.

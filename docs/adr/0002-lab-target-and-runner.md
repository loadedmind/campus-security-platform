# ADR-0002: Lab target, control node and transport security

**Status:** accepted (lab); production path noted

## Context
The lab is one Windows 11 desktop with Hyper-V and one always-on Ubuntu mini PC. Ansible's control node cannot run natively on Windows.

## Decision
- **Hyper-V host:** runs only VMs. Terraform reaches it over WinRM HTTPS (5986) with a dedicated local account, firewall-scoped to the automation host.
- **Automation host (Linux):** the single self-hosted GitHub Actions runner (label `campus-lab`), the Ansible/Terraform control node, and the observability stack.
- **Guests:** WinRM over HTTPS only (HTTP listener removed at first boot), NTLM, self-signed certificates.

## Consequences
- Self-signed certificates force `server_cert_validation: ignore` and provider `insecure = true`. Acceptable on an isolated home LAN; not acceptable in production, where hosts enrol from an internal CA and validation is on.
- `LocalAccountTokenFilterPolicy=1` on the Hyper-V host lets a local admin account manage Hyper-V remotely. Production uses domain accounts and JEA endpoints instead.
- One runner = one path for deploy, patch and remediation. The `RemediatorDown` and dispatch-failure alerts make loss of that path visible.

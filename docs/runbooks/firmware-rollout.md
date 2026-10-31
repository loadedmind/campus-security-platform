# Runbook: device firmware rollout

1. PR: change the version for one device type in `fleet/firmware.yaml`.
2. Merge. `observability` regenerates the drift rules and reloads Prometheus.
3. After 10 minutes `DeviceFirmwareDrift` fires once per host for that type; the relay dispatches `push_firmware`, which updates devices in 25 % batches and stops if a batch does not return online on the new version.
4. Caps apply (2 runs per host per hour), so a large campus converges over several runs. Track progress in the Grafana "Firmware versions in the fleet" table.

**Stop a rollout:** revert the PR. Drift alerts now point at the old version and the same loop converges back.

**Alert fired for a single device that drifted on its own:** same path; no action needed unless it repeats.

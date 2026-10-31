# Game day: break it on purpose

Run from the automation host. `TOKEN` is the simulator API token (GitHub secret `SIM_API_TOKEN`), `HOST` a campus host IP.

| Fault | Inject | Expected platform response |
|---|---|---|
| Service stopped | On the campus host: `Stop-Service CampusSecSim` | `CampusSecSimServiceDown` (2 min) -> `restart_sim_service` run -> alert clears |
| Device offline | `curl -X POST -H "Authorization: Bearer $TOKEN" -d '{"fault":"device_offline","device_id":"camera-0003"}' http://$HOST:8080/api/v1/faults` | `DevicesOffline` (5 min) -> `reboot_offline_devices` -> device back in ~20 s |
| Firmware drift | same endpoint, `"fault":"firmware_drift"` | `DeviceFirmwareDrift` (10 min) -> `push_firmware` batch -> version restored |
| Mass outage | inject `device_offline` on >50 % of one host's devices | `MassDeviceOutage` pages a human; `DevicesOffline` is inhibited; no automatic reboots |
| Camera not recording | `"fault":"recording_stopped"` on a camera | `CameraNotRecording` pages a human; never auto-remediated |
| Remediation loop | stop the service 4 times within an hour | 4th time: relay suppresses, `RemediationSuppressed` pages |
| Config drift | On the campus host: `Remove-NetFirewallRule -Name Campus-SecSim-In` | DSC LCM restores the rule within 15 min; no pipeline run |

Record for each: time to detect, time to recover, whether a human was needed. Those numbers are the on-call load the automation removed.

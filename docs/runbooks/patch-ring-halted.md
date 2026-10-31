# Runbook: patch run halted

A ring failed its install or health gate. Its VMs were restored to the pre-patch checkpoint automatically and later rings did not run.

1. Open the failed `patch` run. The step summary and Ansible output show which host and which update failed, or which alert held the gate red.
2. Check the ring's hosts in Grafana: all `up`, no critical alerts after the restore.
3. Decide:
   - **Bad update:** decline it in WSUS (`Deny-WsusUpdate`), then re-run `patch` with `start_ring` = the failed ring and `approvals_run_id` = the original run id; the declined update is skipped because it no longer reports as needed.
   - **Unrelated fault during the window:** fix it, then resume the same way.
4. Checkpoints named `prepatch-<run id>` are pruned automatically when that ring is checkpointed on the next run.

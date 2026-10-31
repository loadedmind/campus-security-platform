#!/usr/bin/env bash
# Regenerate everything derived from Terraform outputs + repo policy:
#   * Ansible inventory (copied into ansible/inventory/hosts.yml)
#   * Prometheus file_sd targets
#   * Prometheus firmware rules (+ hot reload)
# Runs on: the automation host (self-hosted runner), from the repo root.
set -euo pipefail

: "${CAMPUS_STATE_DIR:?CAMPUS_STATE_DIR must be set}"
: "${HYPERV_HOST:?HYPERV_HOST must be set}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:19090}"

mkdir -p "${CAMPUS_STATE_DIR}/outputs" "${CAMPUS_STATE_DIR}/prometheus/targets" \
         "${CAMPUS_STATE_DIR}/prometheus/rules-generated"

python3 scripts/render_inventory.py --state-dir "${CAMPUS_STATE_DIR}" --hyperv-host "${HYPERV_HOST}"
cp "${CAMPUS_STATE_DIR}/inventory/hosts.yml" ansible/inventory/hosts.yml

python3 scripts/render_firmware_rules.py \
  --out "${CAMPUS_STATE_DIR}/prometheus/rules-generated/firmware.rules.yml"

# Rules need an explicit reload; file_sd targets are picked up automatically.
if curl -fsS -X POST "${PROMETHEUS_URL}/-/reload" >/dev/null 2>&1; then
  echo "prometheus reloaded"
else
  echo "::warning::could not reload Prometheus at ${PROMETHEUS_URL} (is the observability stack up?)"
fi

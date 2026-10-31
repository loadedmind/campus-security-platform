#!/usr/bin/env bash
# Post-deploy health gate for one site, judged by Prometheus (the same signal
# on-call would use), not by the deploy tool's own exit code.
# Usage: scripts/smoke_test.sh <site>
# Runs on: the automation host (self-hosted runner), from the repo root.
set -euo pipefail

site="${1:?usage: smoke_test.sh <site>}"
[[ "$site" =~ ^([a-z]{3}-[0-9]{2}|core)$ ]] || { echo "bad site: $site"; exit 1; }
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:19090}"
group="site_${site//-/_}"

hosts="$(python3 scripts/group_hosts.py --inventory ansible/inventory/hosts.yml --group "$group")"
echo "smoke testing ${site}: ${hosts}"

# 1. Every host scraped and up, held for 2 minutes.
python3 scripts/prom_wait.py --prometheus "$PROMETHEUS_URL" \
  --expr "up{job=\"windows\",host=~\"${hosts}\"}" --expect all-ones --timeout 600 --stable 120

# 2. Simulator API up on application hosts (none on core).
if [[ "$site" != "core" ]]; then
  python3 scripts/prom_wait.py --prometheus "$PROMETHEUS_URL" \
    --expr "up{job=\"campus_sim\",host=~\"${hosts}\"}" --expect all-ones --timeout 300 --stable 120
fi

# 3. No critical alert firing for these hosts, held for 3 minutes.
python3 scripts/prom_wait.py --prometheus "$PROMETHEUS_URL" \
  --expr "ALERTS{alertstate=\"firing\",severity=\"critical\",host=~\"${hosts}\"}" \
  --expect empty --timeout 600 --stable 180

echo "smoke test passed for ${site}"

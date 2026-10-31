#!/usr/bin/env bash
# One-time preparation of the Linux automation host (self-hosted runner +
# observability stack). Idempotent.
#
#   * installs OS packages (docker, compose, python venv, gh, unzip, jq)
#   * creates the runner service account and state directory
#   * generates the shared secrets the observability stack needs
#
# Run on: the automation host (bee), as a sudo-capable user:
#   sudo ./scripts/bootstrap-automation-host.sh loadedmind/campus-security-platform
set -euo pipefail

REPO="${1:?usage: bootstrap-automation-host.sh <owner/repo>}"
RUNNER_USER="${RUNNER_USER:-campus-runner}"
STATE_DIR="${CAMPUS_STATE_DIR:-/var/lib/campus-platform}"

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ "$REPO" =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]] || { echo "bad repo: $REPO" >&2; exit 1; }

echo "==> packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  docker.io docker-compose-v2 python3 python3-venv python3-pip gh unzip jq curl git

echo "==> runner account ${RUNNER_USER}"
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$RUNNER_USER"
fi
usermod -aG docker "$RUNNER_USER"

echo "==> state directory ${STATE_DIR}"
install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$STATE_DIR"
for d in tfstate plans outputs inventory releases lkg patch prometheus/targets prometheus/rules-generated; do
  install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$STATE_DIR/$d"
done
install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0700 "$STATE_DIR/secrets"
for f in windows campus_sim; do
  t="$STATE_DIR/prometheus/targets/$f.json"
  [[ -f "$t" ]] || { echo '[]' > "$t"; chown "$RUNNER_USER:$RUNNER_USER" "$t"; }
done

echo "==> secrets"
umask 077
if [[ ! -s "$STATE_DIR/secrets/webhook_token" ]]; then
  openssl rand -hex 32 > "$STATE_DIR/secrets/webhook_token"
fi
if [[ ! -s "$STATE_DIR/secrets/grafana.env" ]]; then
  echo "GF_SECURITY_ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')" > "$STATE_DIR/secrets/grafana.env"
fi
if [[ ! -s "$STATE_DIR/secrets/remediator.env" ]]; then
  read -r -s -p "Fine-grained GitHub token for ${REPO} (Contents: read and write): " gh_token; echo
  {
    echo "GITHUB_REPOSITORY=${REPO}"
    echo "GITHUB_TOKEN=${gh_token}"
    echo "WEBHOOK_TOKEN=$(cat "$STATE_DIR/secrets/webhook_token")"
    echo "DRY_RUN=false"
  } > "$STATE_DIR/secrets/remediator.env"
fi
# Alertmanager runs as uid 65534 (nobody) in its image and must read the token.
chmod 0644 "$STATE_DIR/secrets/webhook_token"
chown -R "$RUNNER_USER:$RUNNER_USER" "$STATE_DIR/secrets"

echo
echo "Automation host ready."
echo "  state dir:     $STATE_DIR"
echo "  runner user:   $RUNNER_USER (in group docker)"
echo "  grafana admin: see $STATE_DIR/secrets/grafana.env"
echo "Next: register the GitHub Actions runner as ${RUNNER_USER} with label 'campus-lab'."

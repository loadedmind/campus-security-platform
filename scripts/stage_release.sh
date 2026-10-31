#!/usr/bin/env bash
# Download a platform release's packages from GitHub Releases into the control
# node cache and verify every checksum. Idempotent.
# Usage: scripts/stage_release.sh v1.2.0
# Runs on: the automation host (self-hosted runner). Needs GH_TOKEN.
set -euo pipefail

release="${1:?usage: stage_release.sh vX.Y.Z}"
[[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "::error::bad release tag: $release"; exit 1; }
: "${CAMPUS_STATE_DIR:?CAMPUS_STATE_DIR must be set}"

dest="${CAMPUS_STATE_DIR}/releases/${release}"
if [[ -f "${dest}/SHA256SUMS" ]] && (cd "$dest" && sha256sum --quiet -c SHA256SUMS); then
  echo "release ${release} already staged and verified"
  exit 0
fi

mkdir -p "${CAMPUS_STATE_DIR}/releases"
tmp="$(mktemp -d "${CAMPUS_STATE_DIR}/releases/.staging-XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
gh release download "$release" --repo "${GITHUB_REPOSITORY:?}" --dir "$tmp" \
  --pattern '*.nupkg' --pattern 'SHA256SUMS'
(cd "$tmp" && sha256sum -c SHA256SUMS)

rm -rf "$dest"
mv "$tmp" "$dest"
trap - EXIT
echo "staged ${release} -> ${dest}"

#!/usr/bin/env python3
"""Validate a repository_dispatch remediation payload before anything runs.

Defense in depth behind the relay: the payload is attacker-reachable by anyone
holding a token with Contents:write, so the workflow re-checks it here against
the catalog and the live inventory. Values are read from environment variables
(never interpolated into shell) and the validated result is written to
GITHUB_OUTPUT.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml

from platform_lib import REPO_ROOT, load_yaml

VALUE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ALERTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def validate(payload: dict, catalog: dict, inventory_hosts: set[str]) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    remediations = catalog.get("remediations", {})
    key = str(payload.get("remediation", ""))
    spec = remediations.get(key)
    if spec is None:
        return {}, [f"remediation '{key[:40]}' is not in remediation/catalog.yaml"]

    host = str(payload.get("host", ""))
    if not VALUE_RE.match(host):
        errors.append("host label is malformed")
    elif host not in inventory_hosts:
        errors.append(f"host '{host}' is not in the current inventory")

    extra_in = payload.get("extra_vars", {}) or {}
    if not isinstance(extra_in, dict):
        errors.append("extra_vars must be an object")
        extra_in = {}
    allowed = set(spec.get("pass_labels", []) or [])
    unexpected = set(extra_in) - allowed
    if unexpected:
        errors.append(f"unexpected extra_vars: {sorted(unexpected)}")
    extra: dict[str, str] = {}
    for name in allowed:
        value = str(extra_in.get(name, ""))
        if not VALUE_RE.match(value):
            errors.append(f"extra var '{name}' missing or malformed")
        else:
            extra[name] = value

    alertname = str(payload.get("alertname", ""))
    if not ALERTNAME_RE.match(alertname):
        errors.append("alertname is missing or malformed")

    result = {
        "playbook": spec["playbook"],
        "host": host,
        "alertname": alertname,
        "extra_vars_json": json.dumps(extra, sort_keys=True),
    }
    return result, errors


def main() -> int:
    payload = json.loads(os.environ.get("REMEDIATION_PAYLOAD", "{}") or "{}")
    catalog = load_yaml(REPO_ROOT / "remediation" / "catalog.yaml")
    inventory_path = Path(os.environ["INVENTORY_FILE"])
    inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    hosts = set(inventory["all"]["children"]["windows"]["hosts"].keys())

    result, errors = validate(payload, catalog, hosts)
    for err in errors:
        print(f"::error::{err}")
    if errors:
        return 1
    out_path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in result.items()]
    if out_path:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

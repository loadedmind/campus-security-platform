#!/usr/bin/env python3
"""Generate Prometheus firmware-drift rules from fleet/firmware.yaml.

The desired versions live in one reviewed file; the alert expression is derived
from it so policy and detection cannot disagree.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from platform_lib import REPO_ROOT, load_yaml, write_yaml

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
TYPE_RE = re.compile(r"^[a-z]+$")


def build_rules(policy: dict[str, Any]) -> dict[str, Any]:
    desired = policy.get("desired", {})
    if not desired:
        raise ValueError("fleet/firmware.yaml: 'desired' is empty")
    rules = []
    for device_type, version in sorted(desired.items()):
        version = str(version)
        if not TYPE_RE.match(device_type) or not VERSION_RE.match(version):
            raise ValueError(f"invalid policy entry {device_type}: {version}")
        rules.append(
            {
                "alert": "DeviceFirmwareDrift",
                # Aggregated per host + type: one remediation run converges the batch.
                "expr": (
                    f'count by (site, host, device_type) ('
                    f'campus_sim_device_firmware_info{{device_type="{device_type}",version!="{version}"}}'
                    f' unless on (site, host, device_id) campus_sim_device_maintenance == 1) > 0'
                ),
                "for": "10m",
                "labels": {
                    "severity": "warning",
                    "remediation": "push_firmware",
                    "desired_version": version,
                },
                "annotations": {
                    "summary": f"{{{{ $value }}}} {device_type} device(s) on {{{{ $labels.host }}}} not on firmware {version}",
                    "runbook_url": "https://github.com/loadedmind/campus-security-platform/blob/main/docs/runbooks/firmware-rollout.md",
                },
            }
        )
    return {"groups": [{"name": "fleet-firmware-policy (generated)", "rules": rules}]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=REPO_ROOT / "fleet" / "firmware.yaml")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_yaml(args.out, build_rules(load_yaml(args.policy)))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

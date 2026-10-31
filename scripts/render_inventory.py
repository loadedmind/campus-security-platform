#!/usr/bin/env python3
"""Build the Ansible inventory and Prometheus file_sd targets from Terraform outputs.

Input:  <state-dir>/outputs/<site>.json   (written by `terraform output -json site`)
        sites/<site>.yaml                 (desired state, for release + device counts)
Output: <state-dir>/inventory/hosts.yml   (Ansible)
        <state-dir>/prometheus/targets/windows.json
        <state-dir>/prometheus/targets/campus_sim.json

One generator for both consumers means a host can never be configured but not
monitored, or monitored but not configured.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path
from typing import Any

from platform_lib import SITES_DIR, ansible_group, load_sites, write_json, write_yaml

WINDOWS_EXPORTER_PORT = 9182
SIM_PORT = 8080


def load_outputs(outputs_dir: Path) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for path in sorted(outputs_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("name") != path.stem:
            raise ValueError(f"{path}: output name {data.get('name')!r} does not match file name")
        outputs[path.stem] = data
    return outputs


def build(outputs: dict[str, dict[str, Any]], sites: dict[str, dict[str, Any]],
          hyperv_host: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    hostvars: dict[str, dict[str, Any]] = {}
    groups: dict[str, set[str]] = {}
    windows_targets: list[dict[str, Any]] = []
    sim_targets: list[dict[str, Any]] = []

    for site_name, out in sorted(outputs.items()):
        site = sites.get(site_name)
        if site is None:
            # Site file removed but VMs still exist: keep monitoring until torn down.
            print(f"warning: {site_name} has outputs but no site file (pending teardown?)", file=sys.stderr)
            site = {"platform": {}}
        for host_name, h in sorted(out["hosts"].items()):
            ip = h.get("ipv4_address")
            if not ip:
                raise ValueError(f"{site_name}/{host_name}: no IPv4 address in Terraform output")
            ipaddress.IPv4Address(ip)  # raises on garbage
            ring = int(out["patch_ring"])
            role = h["role"]
            platform = site.get("platform", {}) or {}
            hostvars[host_name] = {
                "ansible_host": ip,
                "site": site_name,
                "site_kind": out["kind"],
                "site_timezone": site.get("timezone", "UTC"),
                "role": role,
                "patch_ring": ring,
                "image": out["image"],
                "platform_release": platform.get("release"),
                "sim_devices": platform.get("devices", {}),
            }
            for group in (
                "windows",
                ansible_group("site", site_name),
                ansible_group("role", role),
                ansible_group("ring", ring),
            ):
                groups.setdefault(group, set()).add(host_name)

            labels = {"host": host_name, "site": site_name, "role": role, "ring": str(ring)}
            windows_targets.append({"targets": [f"{ip}:{WINDOWS_EXPORTER_PORT}"], "labels": labels})
            if role == "secapp":
                sim_targets.append({"targets": [f"{ip}:{SIM_PORT}"], "labels": labels})

    children: dict[str, Any] = {}
    for group, members in sorted(groups.items()):
        if group == "windows":
            children[group] = {"hosts": {name: hostvars[name] for name in sorted(members)}}
        else:
            children[group] = {"hosts": {name: None for name in sorted(members)}}
    children["hyperv_hosts"] = {"hosts": {"hyperv01": {"ansible_host": hyperv_host}}}

    inventory = {"all": {"children": children}}
    return inventory, windows_targets, sim_targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--hyperv-host", required=True)
    parser.add_argument("--sites-dir", type=Path, default=SITES_DIR)
    args = parser.parse_args()

    outputs = load_outputs(args.state_dir / "outputs")
    if not outputs:
        print("no Terraform outputs found; nothing to render", file=sys.stderr)
        return 1
    inventory, windows_targets, sim_targets = build(outputs, load_sites(args.sites_dir), args.hyperv_host)

    write_yaml(args.state_dir / "inventory" / "hosts.yml", inventory)
    write_json(args.state_dir / "prometheus" / "targets" / "windows.json", windows_targets)
    write_json(args.state_dir / "prometheus" / "targets" / "campus_sim.json", sim_targets)
    hosts = len(inventory["all"]["children"]["windows"]["hosts"])
    print(f"rendered inventory for {hosts} hosts across {len(outputs)} sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())

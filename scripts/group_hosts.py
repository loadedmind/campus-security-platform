#!/usr/bin/env python3
"""Print the hosts of an inventory group as a PromQL regex alternation.

  python scripts/group_hosts.py --inventory ansible/inventory/hosts.yml --group ring_0
  -> hou01-sec01|hou02-sec01   (exit 1 if the group is empty)

PromQL regex matchers are fully anchored, so `host=~"<output>"` matches exactly
these hosts.

Used to scope health gates to exactly the hosts a pipeline step touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

HOST_RE = re.compile(r"^[a-z0-9-]{1,15}$")


def hosts_in_group(inventory: dict, group: str) -> list[str]:
    children = inventory["all"]["children"]
    members = (children.get(group) or {}).get("hosts") or {}
    hosts = sorted(members)
    for h in hosts:
        if not HOST_RE.match(h):
            raise ValueError(f"unexpected host name {h!r}")
    return hosts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--group", required=True)
    args = parser.parse_args()
    hosts = hosts_in_group(yaml.safe_load(args.inventory.read_text(encoding="utf-8")), args.group)
    if not hosts:
        print(f"group {args.group} has no hosts", file=sys.stderr)
        return 1
    print("|".join(hosts))
    return 0


if __name__ == "__main__":
    sys.exit(main())

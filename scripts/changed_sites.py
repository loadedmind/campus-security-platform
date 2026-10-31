#!/usr/bin/env python3
"""Decide which sites a push to main must deploy.

Rules:
  * sites/<x>.yaml changed            -> deploy <x>
  * shared code changed               -> deploy every site (core first)
  * sites/<x>.yaml deleted            -> never auto-destroy; flagged for the
                                         manual teardown workflow
Prints GitHub Actions outputs: core=<true|false>, campuses=<json list>, removed=<json list>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from platform_lib import REPO_ROOT, SITE_NAME_RE, load_sites

SHARED_PREFIXES = (
    "terraform/",
    "ansible/roles/",
    "ansible/playbooks/site.yml",
    "ansible/inventory/group_vars/",
    "ansible/requirements.yml",
    "ansible/requirements.txt",
    "dsc/",
)


def classify(changed: list[str], deleted: list[str], sites: dict[str, dict]) -> dict[str, object]:
    core_names = sorted(n for n, s in sites.items() if s.get("kind") == "core")
    campus_names = sorted(n for n, s in sites.items() if s.get("kind") == "campus")

    if any(path.startswith(SHARED_PREFIXES) for path in changed):
        return {"core": bool(core_names), "campuses": campus_names, "removed": []}

    selected: set[str] = set()
    removed: list[str] = []
    for path in changed:
        p = Path(path)
        if p.parent.as_posix() == "sites" and p.suffix == ".yaml" and not p.name.startswith("_"):
            if path in deleted:
                removed.append(p.stem)
            elif SITE_NAME_RE.match(p.stem):
                selected.add(p.stem)
    return {
        "core": any(n in selected for n in core_names),
        "campuses": sorted(n for n in selected if n in campus_names),
        "removed": sorted(removed),
    }


def git_diff(base: str, head: str, diff_filter: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"--diff-filter={diff_filter}", base, head],
        check=True, capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit (github.event.before)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--site", default="", help="explicit site (workflow_dispatch)")
    args = parser.parse_args()

    sites = load_sites()
    if args.site:
        if args.site not in sites:
            print(f"::error::unknown site {args.site}")
            return 1
        kind = sites[args.site]["kind"]
        result = {"core": kind == "core", "campuses": [args.site] if kind == "campus" else [], "removed": []}
    elif set(args.base) == {"0"}:
        # First push of a branch: no usable base; deploy everything.
        result = classify(["terraform/"], [], sites)
    else:
        changed = git_diff(args.base, args.head, "ACMRD")
        deleted = git_diff(args.base, args.head, "D")
        result = classify(changed, deleted, sites)

    lines = [
        f"core={'true' if result['core'] else 'false'}",
        f"campuses={json.dumps(result['campuses'])}",
        f"removed={json.dumps(result['removed'])}",
    ]
    out_path = os.environ.get("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    for name in result["removed"]:
        print(f"::warning::site file {name}.yaml removed; run the teardown workflow to destroy its VMs")
    return 0


if __name__ == "__main__":
    sys.exit(main())

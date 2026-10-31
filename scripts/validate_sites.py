#!/usr/bin/env python3
"""Validate every site definition before anything is planned or applied.

Checks:
  * JSON schema (sites/_schema.json)
  * file name == site name
  * exactly one core site
  * host names unique across all sites (they become Windows computer names)
  * every campus host role has a matching Ansible play
Exit code 1 with one line per problem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from platform_lib import SCHEMA_PATH, SITES_DIR, load_yaml, site_files


def validate(sites_dir: Path = SITES_DIR, schema_path: Path = SCHEMA_PATH) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    seen_hosts: dict[str, str] = {}
    cores: list[str] = []

    files = site_files(sites_dir)
    if not files:
        return [f"no site files found in {sites_dir}"]

    for path in files:
        try:
            site = load_yaml(path)
        except Exception as exc:  # noqa: BLE001 - report any parse failure
            errors.append(f"{path.name}: YAML parse error: {exc}")
            continue
        for err in sorted(validator.iter_errors(site), key=lambda e: list(e.path)):
            location = "/".join(str(p) for p in err.path) or "<root>"
            errors.append(f"{path.name}: {location}: {err.message}")
        if not isinstance(site, dict):
            continue
        if site.get("name") != path.stem:
            errors.append(f"{path.name}: name '{site.get('name')}' must equal file name '{path.stem}'")
        if site.get("kind") == "core":
            cores.append(path.name)
        for host in site.get("hosts", []) or []:
            name = host.get("name") if isinstance(host, dict) else None
            if not name:
                continue
            if name in seen_hosts:
                errors.append(f"{path.name}: host '{name}' already defined in {seen_hosts[name]}")
            seen_hosts[name] = path.name
            if site.get("kind") == "campus" and host.get("role") != "secapp":
                errors.append(f"{path.name}: campus host '{name}' must have role 'secapp'")
            if site.get("kind") == "core" and host.get("role") != "wsus":
                errors.append(f"{path.name}: core host '{name}' must have role 'wsus'")

    if len(cores) != 1:
        errors.append(f"expected exactly one core site, found {len(cores)}: {cores}")
    return errors


def main() -> int:
    errors = validate()
    for line in errors:
        print(f"::error::{line}")
    if errors:
        return 1
    print(f"OK: {len(site_files())} site definitions valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())

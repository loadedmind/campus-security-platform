"""Shared helpers for pipeline scripts. Stdlib + PyYAML + jsonschema only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SITES_DIR = REPO_ROOT / "sites"
SCHEMA_PATH = SITES_DIR / "_schema.json"

SITE_NAME_RE = re.compile(r"^([a-z]{3}-[0-9]{2}|core)$")


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def site_files(sites_dir: Path = SITES_DIR) -> list[Path]:
    return sorted(p for p in sites_dir.glob("*.yaml") if not p.name.startswith("_"))


def load_sites(sites_dir: Path = SITES_DIR) -> dict[str, dict[str, Any]]:
    return {p.stem: load_yaml(p) for p in site_files(sites_dir)}


def ansible_group(prefix: str, value: str | int) -> str:
    """Ansible group names must be valid identifiers: hou-01 -> site_hou_01."""
    return f"{prefix}_{str(value).replace('-', '_')}"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic: Prometheus file_sd never reads a half-written file


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=True, default_flow_style=False), encoding="utf-8")
    tmp.replace(path)

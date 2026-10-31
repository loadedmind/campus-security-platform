"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEVICE_TYPES = ("camera", "door", "reader", "controller")


class ConfigError(ValueError):
    """Raised when the simulator configuration is invalid."""


@dataclass(frozen=True)
class SimConfig:
    site: str
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    api_token: str = ""
    devices: dict[str, int] = field(default_factory=dict)
    initial_firmware: dict[str, str] = field(default_factory=dict)
    access_events_per_minute: float = 30.0
    access_denied_ratio: float = 0.05
    reboot_seconds: float = 20.0
    firmware_update_seconds: float = 45.0
    tick_seconds: float = 1.0
    random_seed: int | None = None


def _require(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"missing required key: {key}")
    return mapping[key]


def parse_config(raw: dict[str, Any]) -> SimConfig:
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    site = str(_require(raw, "site")).strip()
    if not site:
        raise ConfigError("site must be a non-empty string")

    devices_raw = _require(raw, "devices")
    if not isinstance(devices_raw, dict):
        raise ConfigError("devices must be a mapping of device_type -> count")
    devices: dict[str, int] = {}
    for dtype, count in devices_raw.items():
        if dtype not in DEVICE_TYPES:
            raise ConfigError(f"unknown device type: {dtype}")
        if not isinstance(count, int) or count < 0 or count > 10000:
            raise ConfigError(f"device count for {dtype} must be an int in 0..10000")
        devices[dtype] = count

    firmware_raw = raw.get("initial_firmware", {}) or {}
    if not isinstance(firmware_raw, dict):
        raise ConfigError("initial_firmware must be a mapping")
    firmware: dict[str, str] = {}
    for dtype in devices:
        firmware[dtype] = str(firmware_raw.get(dtype, "1.0.0"))

    api_token = str(raw.get("api_token", ""))
    if api_token and len(api_token) < 16:
        raise ConfigError("api_token must be at least 16 characters when set")

    port = int(raw.get("listen_port", 8080))
    if not 1 <= port <= 65535:
        raise ConfigError("listen_port must be 1..65535")

    ratio = float(raw.get("access_denied_ratio", 0.05))
    if not 0.0 <= ratio <= 1.0:
        raise ConfigError("access_denied_ratio must be 0..1")

    seed = raw.get("random_seed")
    return SimConfig(
        site=site,
        listen_host=str(raw.get("listen_host", "0.0.0.0")),
        listen_port=port,
        api_token=api_token,
        devices=devices,
        initial_firmware=firmware,
        access_events_per_minute=float(raw.get("access_events_per_minute", 30.0)),
        access_denied_ratio=ratio,
        reboot_seconds=float(raw.get("reboot_seconds", 20.0)),
        firmware_update_seconds=float(raw.get("firmware_update_seconds", 45.0)),
        tick_seconds=float(raw.get("tick_seconds", 1.0)),
        random_seed=int(seed) if seed is not None else None,
    )


def load_config(path: str | Path) -> SimConfig:
    text = Path(path).read_text(encoding="utf-8")
    return parse_config(yaml.safe_load(text))

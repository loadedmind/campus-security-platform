"""In-memory model of a campus security device fleet.

All state transitions go through Fleet methods under a single lock, and time is
injected through a clock callable so tests are deterministic.
"""

from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .config import SimConfig

DEVICE_ID_RE = re.compile(r"^[a-z]+-\d{4}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

FAULT_TYPES = ("device_offline", "firmware_drift", "recording_stopped")


class FleetError(Exception):
    """Base error for fleet operations."""


class UnknownDevice(FleetError):
    pass


class InvalidRequest(FleetError):
    pass


@dataclass
class Device:
    device_id: str
    device_type: str
    firmware: str
    online: bool = True
    faulted: bool = False
    recording: bool = True  # meaningful for cameras only
    busy_until: float = 0.0
    pending_firmware: str | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "firmware": self.firmware,
            "online": self.online,
            "faulted": self.faulted,
            "busy": self.busy_until > 0.0,
        }
        if self.device_type == "camera":
            data["recording"] = self.recording
        return data


@dataclass
class Fleet:
    config: SimConfig
    clock: Callable[[], float] = time.monotonic
    rng: random.Random = field(default_factory=random.Random)
    devices: dict[str, Device] = field(default_factory=dict)
    access_events: dict[tuple[str, str], int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _event_debt: float = 0.0

    def __post_init__(self) -> None:
        if self.config.random_seed is not None:
            self.rng.seed(self.config.random_seed)
        for dtype, count in self.config.devices.items():
            for n in range(1, count + 1):
                device_id = f"{dtype}-{n:04d}"
                self.devices[device_id] = Device(
                    device_id=device_id,
                    device_type=dtype,
                    firmware=self.config.initial_firmware[dtype],
                )
                if dtype == "door":
                    self.access_events[(device_id, "granted")] = 0
                    self.access_events[(device_id, "denied")] = 0

    # ------------------------------------------------------------------ lookup
    def _get(self, device_id: str) -> Device:
        if not DEVICE_ID_RE.match(device_id):
            raise InvalidRequest("malformed device_id")
        try:
            return self.devices[device_id]
        except KeyError as exc:
            raise UnknownDevice(device_id) from exc

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [d.as_dict() for d in self.devices.values()]

    def device(self, device_id: str) -> dict[str, object]:
        with self._lock:
            return self._get(device_id).as_dict()

    def access_event_counts(self) -> dict[tuple[str, str], int]:
        with self._lock:
            return dict(self.access_events)

    # --------------------------------------------------------------- commands
    def reboot(self, device_id: str) -> dict[str, object]:
        """Power-cycle a device. Clears a soft fault after reboot_seconds."""
        with self._lock:
            dev = self._get(device_id)
            if dev.busy_until > 0.0:
                raise InvalidRequest("device is busy")
            dev.online = False
            dev.busy_until = self.clock() + self.config.reboot_seconds
            return dev.as_dict()

    def update_firmware(self, device_id: str, version: str) -> dict[str, object]:
        if not VERSION_RE.match(version):
            raise InvalidRequest("version must be MAJOR.MINOR.PATCH")
        with self._lock:
            dev = self._get(device_id)
            if dev.busy_until > 0.0:
                raise InvalidRequest("device is busy")
            dev.online = False
            dev.pending_firmware = version
            dev.busy_until = self.clock() + self.config.firmware_update_seconds
            return dev.as_dict()

    def inject_fault(self, fault: str, device_id: str) -> dict[str, object]:
        """Fault injection for demos and game days."""
        if fault not in FAULT_TYPES:
            raise InvalidRequest(f"fault must be one of {FAULT_TYPES}")
        with self._lock:
            dev = self._get(device_id)
            if fault == "device_offline":
                dev.online = False
                dev.faulted = True
            elif fault == "firmware_drift":
                major, minor, _patch = dev.firmware.split(".")
                dev.firmware = f"{major}.{int(minor) - 1 if int(minor) > 0 else 0}.99"
            elif fault == "recording_stopped":
                if dev.device_type != "camera":
                    raise InvalidRequest("recording_stopped applies to cameras only")
                dev.recording = False
            return dev.as_dict()

    # ------------------------------------------------------------------- tick
    def tick(self, elapsed: float) -> None:
        """Advance simulation: finish reboots/updates and emit access events."""
        now = self.clock()
        with self._lock:
            for dev in self.devices.values():
                if dev.busy_until > 0.0 and now >= dev.busy_until:
                    dev.busy_until = 0.0
                    if dev.pending_firmware is not None:
                        dev.firmware = dev.pending_firmware
                        dev.pending_firmware = None
                    dev.faulted = False
                    dev.online = True
                    if dev.device_type == "camera":
                        dev.recording = True

            doors = [d for d in self.devices.values() if d.device_type == "door" and d.online]
            if not doors:
                return
            self._event_debt += self.config.access_events_per_minute * elapsed / 60.0
            while self._event_debt >= 1.0:
                self._event_debt -= 1.0
                door = self.rng.choice(doors)
                result = "denied" if self.rng.random() < self.config.access_denied_ratio else "granted"
                self.access_events[(door.device_id, result)] += 1

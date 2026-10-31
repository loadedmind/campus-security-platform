"""Prometheus exposition for the simulated fleet."""

from __future__ import annotations

from typing import Iterator

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector, CollectorRegistry

from . import __version__
from .fleet import Fleet


class FleetCollector(Collector):
    def __init__(self, fleet: Fleet) -> None:
        self.fleet = fleet

    def collect(self) -> Iterator[GaugeMetricFamily | CounterMetricFamily]:
        site = self.fleet.config.site
        devices = self.fleet.snapshot()

        build = GaugeMetricFamily(
            "campus_sim_build_info", "Simulator build information.", labels=["site", "version"]
        )
        build.add_metric([site, __version__], 1)
        yield build

        up = GaugeMetricFamily(
            "campus_sim_device_up",
            "1 if the device is online, 0 otherwise.",
            labels=["site", "device_id", "device_type"],
        )
        firmware = GaugeMetricFamily(
            "campus_sim_device_firmware_info",
            "Firmware version currently running on the device (constant 1).",
            labels=["site", "device_id", "device_type", "version"],
        )
        busy = GaugeMetricFamily(
            "campus_sim_device_maintenance",
            "1 while the device is rebooting or applying firmware.",
            labels=["site", "device_id", "device_type"],
        )
        recording = GaugeMetricFamily(
            "campus_sim_camera_recording",
            "1 if the camera is recording to the archiver, 0 otherwise.",
            labels=["site", "device_id"],
        )
        for dev in devices:
            dev_id = str(dev["device_id"])
            dtype = str(dev["device_type"])
            up.add_metric([site, dev_id, dtype], 1 if dev["online"] else 0)
            firmware.add_metric([site, dev_id, dtype, str(dev["firmware"])], 1)
            busy.add_metric([site, dev_id, dtype], 1 if dev["busy"] else 0)
            if dtype == "camera":
                recording.add_metric([site, dev_id], 1 if dev["recording"] else 0)
        yield up
        yield firmware
        yield busy
        yield recording

        events = CounterMetricFamily(
            "campus_sim_access_events",
            "Access-control events by door and result.",
            labels=["site", "door_id", "result"],
        )
        for (door_id, result), count in sorted(self.fleet.access_event_counts().items()):
            events.add_metric([site, door_id, result], count)
        yield events


def build_registry(fleet: Fleet) -> CollectorRegistry:
    registry = CollectorRegistry(auto_describe=False)
    registry.register(FleetCollector(fleet))
    return registry

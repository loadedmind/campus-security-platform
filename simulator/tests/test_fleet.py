import pytest

from campus_sec_sim.config import ConfigError, parse_config
from campus_sec_sim.fleet import Fleet, InvalidRequest, UnknownDevice


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_fleet(**overrides):
    raw = {
        "site": "hou-01",
        "devices": {"camera": 2, "door": 2, "controller": 1},
        "initial_firmware": {"camera": "2.8.0", "door": "1.0.0", "controller": "4.2.1"},
        "reboot_seconds": 10,
        "firmware_update_seconds": 30,
        "access_events_per_minute": 60,
        "access_denied_ratio": 0.0,
        "random_seed": 7,
    }
    raw.update(overrides)
    clock = FakeClock()
    return Fleet(parse_config(raw), clock=clock), clock


def test_fleet_builds_devices_with_firmware():
    fleet, _ = make_fleet()
    ids = {d["device_id"] for d in fleet.snapshot()}
    assert ids == {"camera-0001", "camera-0002", "door-0001", "door-0002", "controller-0001"}
    assert fleet.device("controller-0001")["firmware"] == "4.2.1"


def test_reboot_clears_offline_fault_after_delay():
    fleet, clock = make_fleet()
    fleet.inject_fault("device_offline", "camera-0001")
    assert fleet.device("camera-0001")["online"] is False

    fleet.reboot("camera-0001")
    clock.now += 5
    fleet.tick(5)
    assert fleet.device("camera-0001")["online"] is False

    clock.now += 6
    fleet.tick(6)
    dev = fleet.device("camera-0001")
    assert dev["online"] is True
    assert dev["faulted"] is False


def test_firmware_update_applies_after_delay():
    fleet, clock = make_fleet()
    fleet.update_firmware("controller-0001", "4.3.0")
    assert fleet.device("controller-0001")["busy"] is True
    clock.now += 31
    fleet.tick(31)
    dev = fleet.device("controller-0001")
    assert dev["firmware"] == "4.3.0"
    assert dev["online"] is True


def test_firmware_drift_changes_version():
    fleet, _ = make_fleet()
    fleet.inject_fault("firmware_drift", "camera-0002")
    assert fleet.device("camera-0002")["firmware"] != "2.8.0"


def test_busy_device_rejects_second_command():
    fleet, _ = make_fleet()
    fleet.reboot("door-0001")
    with pytest.raises(InvalidRequest):
        fleet.update_firmware("door-0001", "1.1.0")


def test_input_validation():
    fleet, _ = make_fleet()
    with pytest.raises(InvalidRequest):
        fleet.update_firmware("camera-0001", "not-a-version")
    with pytest.raises(InvalidRequest):
        fleet.reboot("../../etc")
    with pytest.raises(UnknownDevice):
        fleet.reboot("camera-9999")
    with pytest.raises(InvalidRequest):
        fleet.inject_fault("recording_stopped", "door-0001")


def test_access_events_accumulate():
    fleet, clock = make_fleet()
    clock.now += 60
    fleet.tick(60)
    counts = fleet.access_event_counts()
    assert sum(v for (door, result), v in counts.items() if result == "granted") == 60
    assert sum(v for (door, result), v in counts.items() if result == "denied") == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"devices": {"camera": 1}},  # no site
        {"site": "x", "devices": {"toaster": 1}},
        {"site": "x", "devices": {"camera": -1}},
        {"site": "x", "devices": {"camera": 1}, "api_token": "short"},
        {"site": "x", "devices": {"camera": 1}, "listen_port": 70000},
    ],
)
def test_config_rejects_invalid(bad):
    with pytest.raises(ConfigError):
        parse_config(bad)

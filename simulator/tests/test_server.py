import json
import urllib.error
import urllib.request

import pytest

from campus_sec_sim.config import parse_config
from campus_sec_sim.fleet import Fleet
from campus_sec_sim.server import SimulatorServer

TOKEN = "test-token-0123456789"


@pytest.fixture()
def server():
    config = parse_config(
        {
            "site": "hou-01",
            "api_token": TOKEN,
            "devices": {"camera": 1, "door": 1},
            "initial_firmware": {"camera": "2.8.0", "door": "1.0.0"},
            "tick_seconds": 0.05,
        }
    )
    srv = SimulatorServer(Fleet(config), "127.0.0.1", 0, config.api_token)
    srv.start_background()
    yield srv
    srv.shutdown()


def call(srv, method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_healthz(server):
    status, body = call(server, "GET", "/healthz")
    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_metrics_exposes_fleet(server):
    status, body = call(server, "GET", "/metrics")
    assert status == 200
    assert 'campus_sim_device_up{device_id="camera-0001",device_type="camera",site="hou-01"} 1.0' in body
    assert 'campus_sim_device_firmware_info{device_id="door-0001",device_type="door",site="hou-01",version="1.0.0"} 1.0' in body
    assert "campus_sim_access_events_total" in body


def test_mutations_require_token(server):
    status, _ = call(server, "POST", "/api/v1/devices/camera-0001/reboot", body={})
    assert status == 401
    status, _ = call(server, "POST", "/api/v1/devices/camera-0001/reboot", body={}, token="wrong-token-000000")
    assert status == 401


def test_fault_then_reboot(server):
    status, body = call(server, "POST", "/api/v1/faults",
                        body={"fault": "device_offline", "device_id": "camera-0001"}, token=TOKEN)
    assert status == 200
    assert json.loads(body)["online"] is False
    status, _ = call(server, "POST", "/api/v1/devices/camera-0001/reboot", body={}, token=TOKEN)
    assert status == 202


def test_bad_firmware_version_rejected(server):
    status, body = call(server, "POST", "/api/v1/devices/door-0001/firmware",
                        body={"version": "latest"}, token=TOKEN)
    assert status == 400
    assert "MAJOR.MINOR.PATCH" in json.loads(body)["error"]


def test_unknown_device_404(server):
    status, _ = call(server, "GET", "/api/v1/devices/camera-0099")
    assert status == 404

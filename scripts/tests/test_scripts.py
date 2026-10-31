import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from changed_sites import classify  # noqa: E402
from platform_lib import REPO_ROOT, load_sites  # noqa: E402
from prom_wait import wait  # noqa: E402
from render_firmware_rules import build_rules  # noqa: E402
from render_inventory import build  # noqa: E402
from validate_remediation import validate as validate_remediation  # noqa: E402
from validate_sites import validate as validate_sites  # noqa: E402

SITES = load_sites()
CATALOG = yaml.safe_load((REPO_ROOT / "remediation" / "catalog.yaml").read_text())


def test_repo_sites_are_valid():
    assert validate_sites() == []


def test_duplicate_host_detected(tmp_path):
    for name in ("core", "hou-01", "hou-02"):
        (tmp_path / f"{name}.yaml").write_text((REPO_ROOT / "sites" / f"{name}.yaml").read_text())
    dup = yaml.safe_load((tmp_path / "hou-02.yaml").read_text())
    dup["hosts"][0]["name"] = "hou01-sec01"
    (tmp_path / "hou-02.yaml").write_text(yaml.safe_dump(dup))
    errors = validate_sites(tmp_path, REPO_ROOT / "sites" / "_schema.json")
    assert any("already defined" in e for e in errors)


def test_name_must_match_file(tmp_path):
    for name in ("core", "hou-01"):
        (tmp_path / f"{name}.yaml").write_text((REPO_ROOT / "sites" / f"{name}.yaml").read_text())
    (tmp_path / "dal-01.yaml").write_text((REPO_ROOT / "sites" / "hou-02.yaml").read_text())
    errors = validate_sites(tmp_path, REPO_ROOT / "sites" / "_schema.json")
    assert any("must equal file name" in e for e in errors)


@pytest.mark.parametrize(
    ("changed", "deleted", "expected"),
    [
        (["sites/hou-02.yaml"], [], {"core": False, "campuses": ["hou-02"], "removed": []}),
        (["sites/core.yaml"], [], {"core": True, "campuses": [], "removed": []}),
        (["terraform/modules/hyperv-vm/main.tf"], [], {"core": True, "campuses": ["hou-01", "hou-02"], "removed": []}),
        (["README.md", "docs/x.md"], [], {"core": False, "campuses": [], "removed": []}),
        (["sites/old-01.yaml"], ["sites/old-01.yaml"], {"core": False, "campuses": [], "removed": ["old-01"]}),
        (["ansible/remediation/restart_service.yml"], [], {"core": False, "campuses": [], "removed": []}),
    ],
)
def test_changed_sites(changed, deleted, expected):
    assert classify(changed, deleted, SITES) == expected


def fake_outputs():
    return {
        "core": {"name": "core", "kind": "core", "patch_ring": 2, "image": "ws2025-core-2026.11",
                 "hosts": {"core-wsus01": {"role": "wsus", "ipv4_address": "192.168.5.50"}}},
        "hou-01": {"name": "hou-01", "kind": "campus", "patch_ring": 0, "image": "ws2025-core-2026.11",
                   "hosts": {"hou01-sec01": {"role": "secapp", "ipv4_address": "192.168.5.51"}}},
    }


def test_render_inventory_groups_and_targets():
    inventory, win, sim = build(fake_outputs(), SITES, "192.168.5.129")
    children = inventory["all"]["children"]
    assert set(children["windows"]["hosts"]) == {"core-wsus01", "hou01-sec01"}
    assert "hou01-sec01" in children["site_hou_01"]["hosts"]
    assert "hou01-sec01" in children["ring_0"]["hosts"]
    assert "core-wsus01" in children["role_wsus"]["hosts"]
    assert children["windows"]["hosts"]["hou01-sec01"]["platform_release"] == "v1.0.0"
    assert children["hyperv_hosts"]["hosts"]["hyperv01"]["ansible_host"] == "192.168.5.129"
    assert {t["targets"][0] for t in win} == {"192.168.5.50:9182", "192.168.5.51:9182"}
    assert [t["targets"][0] for t in sim] == ["192.168.5.51:8080"]  # only secapp runs the simulator


def test_render_inventory_rejects_missing_ip():
    outputs = fake_outputs()
    outputs["hou-01"]["hosts"]["hou01-sec01"]["ipv4_address"] = None
    with pytest.raises(ValueError):
        build(outputs, SITES, "192.168.5.129")


def test_firmware_rules_cover_every_type():
    policy = yaml.safe_load((REPO_ROOT / "fleet" / "firmware.yaml").read_text())
    rules = build_rules(policy)["groups"][0]["rules"]
    assert len(rules) == len(policy["desired"])
    for rule in rules:
        assert rule["labels"]["remediation"] == "push_firmware"
        assert "count by (site, host, device_type)" in rule["expr"]


def test_firmware_rules_reject_bad_versions():
    with pytest.raises(ValueError):
        build_rules({"desired": {"camera": "latest"}})


def test_validate_remediation_happy_path():
    payload = {"remediation": "push_firmware", "host": "hou01-sec01", "alertname": "DeviceFirmwareDrift",
               "extra_vars": {"device_type": "camera"}}
    result, errors = validate_remediation(payload, CATALOG, {"hou01-sec01"})
    assert errors == []
    assert result["playbook"] == "push_firmware.yml"
    assert json.loads(result["extra_vars_json"]) == {"device_type": "camera"}


@pytest.mark.parametrize(
    "payload",
    [
        {"remediation": "format_c", "host": "hou01-sec01"},
        {"remediation": "restart_sim_service", "host": "not-in-inventory"},
        {"remediation": "restart_sim_service", "host": "hou01-sec01; whoami"},
        {"remediation": "restart_sim_service", "host": "hou01-sec01", "extra_vars": {"ansible_shell": "x"}},
        {"remediation": "push_firmware", "host": "hou01-sec01", "extra_vars": {"device_type": "$(id)"}},
        {"remediation": "restart_sim_service", "host": "hou01-sec01", "alertname": "X\"} or vector(1)"},
    ],
)
def test_validate_remediation_rejects(payload):
    _, errors = validate_remediation(payload, CATALOG, {"hou01-sec01"})
    assert errors


def test_prom_wait_requires_stability():
    t = {"now": 0.0}
    results = iter([[], [{"value": [0, "1"]}], [{"value": [0, "1"]}], [{"value": [0, "1"]}]])
    ok, _ = wait(lambda: next(results), "all-ones", timeout_s=100, interval_s=10, stable_s=15,
                 clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s))
    assert ok


def test_prom_wait_times_out():
    t = {"now": 0.0}
    ok, _ = wait(lambda: [{"value": [0, "0"]}], "all-ones", timeout_s=30, interval_s=10,
                 clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s))
    assert not ok

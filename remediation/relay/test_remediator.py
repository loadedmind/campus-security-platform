from pathlib import Path

import pytest

from remediator import Relay, load_catalog

CATALOG = Path(__file__).resolve().parents[1] / "catalog.yaml"


class Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def __call__(self) -> float:
        return self.now


def alert(remediation="restart_sim_service", host="hou01-sec01", status="firing", **labels):
    base = {"alertname": "CampusSecSimServiceDown", "remediation": remediation, "host": host, "site": "hou-01"}
    base.update(labels)
    return {"status": status, "labels": base, "fingerprint": "abc123"}


@pytest.fixture()
def relay():
    sent = []
    clock = Clock()
    r = Relay(load_catalog(CATALOG), lambda p: sent.append(p) or True, clock=clock)
    return r, sent, clock


def test_catalog_loads_and_playbooks_exist():
    catalog = load_catalog(CATALOG)
    playbook_dir = CATALOG.parents[1] / "ansible" / "remediation"
    for spec in catalog.values():
        assert (playbook_dir / spec.playbook).is_file(), spec.playbook


def test_dispatches_firing_alert(relay):
    r, sent, _ = relay
    r.handle({"alerts": [alert()]})
    assert len(sent) == 1
    assert sent[0]["remediation"] == "restart_sim_service"
    assert sent[0]["host"] == "hou01-sec01"


def test_ignores_resolved_and_unlabelled(relay):
    r, sent, _ = relay
    r.handle({"alerts": [alert(status="resolved"), {"status": "firing", "labels": {"alertname": "X"}}]})
    assert sent == []


def test_rejects_unknown_remediation_and_bad_labels(relay):
    r, sent, _ = relay
    r.handle({"alerts": [alert(remediation="rm_rf"), alert(host="evil; rm -rf /")]})
    assert sent == []
    assert r.counters.suppressed[("rm_rf", "not_in_catalog")] == 1
    assert r.counters.suppressed[("restart_sim_service", "invalid_host_label")] == 1


def test_pass_labels_required_and_forwarded(relay):
    r, sent, _ = relay
    r.handle({"alerts": [alert(remediation="push_firmware")]})  # missing device_type
    assert sent == []
    r.handle({"alerts": [alert(remediation="push_firmware", device_type="camera")]})
    assert sent[0]["extra_vars"] == {"device_type": "camera"}


def test_cooldown_and_hourly_cap(relay):
    r, sent, clock = relay
    r.handle({"alerts": [alert()]})
    r.handle({"alerts": [alert()]})  # inside 300 s cooldown
    assert len(sent) == 1
    clock.now += 301
    r.handle({"alerts": [alert()]})
    clock.now += 301
    r.handle({"alerts": [alert()]})
    clock.now += 301
    r.handle({"alerts": [alert()]})  # 4th within the hour -> capped at 3
    assert len(sent) == 3
    assert r.counters.suppressed[("restart_sim_service", "rate_limited")] == 1
    clock.now += 3600
    r.handle({"alerts": [alert()]})
    assert len(sent) == 4


def test_metrics_render(relay):
    r, _, _ = relay
    r.handle({"alerts": [alert()]})
    text = r.counters.render()
    assert 'remediator_dispatch_total{remediation="restart_sim_service",result="ok"} 1' in text

"""Alertmanager -> GitHub Actions remediation relay.

Receives Alertmanager webhook notifications, keeps only firing alerts that carry
a `remediation` label present in the catalog, applies cooldown and hourly caps,
and fires a `repository_dispatch` so the remediation runs as an audited
GitHub Actions job (same runner, same Ansible, same logs as every other change).

Stdlib HTTP server; PyYAML is the only dependency.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import yaml

LOG = logging.getLogger("remediator")
LABEL_VALUE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class Remediation:
    key: str
    playbook: str
    pass_labels: tuple[str, ...]
    cooldown_s: int
    max_per_hour: int


def load_catalog(path: str | Path) -> dict[str, Remediation]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = raw.get("remediations", {}) if isinstance(raw, dict) else {}
    catalog: dict[str, Remediation] = {}
    for key, spec in items.items():
        if not KEY_RE.match(key):
            raise ValueError(f"invalid remediation key: {key}")
        playbook = str(spec["playbook"])
        if not re.match(r"^[a-z0-9_]+\.yml$", playbook):
            raise ValueError(f"invalid playbook name for {key}: {playbook}")
        catalog[key] = Remediation(
            key=key,
            playbook=playbook,
            pass_labels=tuple(spec.get("pass_labels", []) or []),
            cooldown_s=int(spec.get("cooldown_s", 300)),
            max_per_hour=int(spec.get("max_per_hour", 1)),
        )
    return catalog


@dataclass
class Counters:
    received: int = 0
    dispatched: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    suppressed: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def render(self) -> str:
        lines = [
            "# HELP remediator_alerts_received_total Alerts received from Alertmanager.",
            "# TYPE remediator_alerts_received_total counter",
            f"remediator_alerts_received_total {self.received}",
            "# HELP remediator_dispatch_total Remediation dispatches by outcome.",
            "# TYPE remediator_dispatch_total counter",
        ]
        for (key, result), n in sorted(self.dispatched.items()):
            lines.append(f'remediator_dispatch_total{{remediation="{key}",result="{result}"}} {n}')
        lines += [
            "# HELP remediator_suppressed_total Remediations not dispatched, by reason.",
            "# TYPE remediator_suppressed_total counter",
        ]
        for (key, reason), n in sorted(self.suppressed.items()):
            lines.append(f'remediator_suppressed_total{{remediation="{key}",reason="{reason}"}} {n}')
        return "\n".join(lines) + "\n"


class Relay:
    def __init__(
        self,
        catalog: dict[str, Remediation],
        dispatch: Callable[[dict[str, Any]], bool],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.catalog = catalog
        self.dispatch = dispatch
        self.clock = clock
        self.counters = Counters()
        self._history: dict[tuple[str, ...], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _suppress(self, key: str, reason: str) -> None:
        self.counters.suppressed[(key, reason)] += 1

    def handle(self, notification: dict[str, Any]) -> list[dict[str, Any]]:
        """Process one Alertmanager webhook payload. Returns dispatched payloads."""
        sent: list[dict[str, Any]] = []
        for alert in notification.get("alerts", []) or []:
            with self._lock:
                self.counters.received += 1
            if alert.get("status") != "firing":
                continue
            labels = alert.get("labels", {}) or {}
            key = labels.get("remediation")
            if not key:
                continue
            spec = self.catalog.get(key)
            if spec is None:
                self._suppress(str(key)[:40], "not_in_catalog")
                continue

            host = labels.get("host", "")
            if not LABEL_VALUE_RE.match(host):
                self._suppress(key, "invalid_host_label")
                continue
            extra: dict[str, str] = {}
            valid = True
            for name in spec.pass_labels:
                value = labels.get(name, "")
                if not LABEL_VALUE_RE.match(value):
                    valid = False
                    break
                extra[name] = value
            if not valid:
                self._suppress(key, "invalid_label")
                continue

            target = (key, host, *[extra[n] for n in spec.pass_labels])
            now = self.clock()
            with self._lock:
                history = self._history[target]
                while history and now - history[0] > 3600:
                    history.popleft()
                if history and now - history[-1] < spec.cooldown_s:
                    self._suppress(key, "cooldown")
                    continue
                if len(history) >= spec.max_per_hour:
                    self._suppress(key, "rate_limited")
                    LOG.warning("rate limit reached for %s; human escalation", target)
                    continue
                history.append(now)

            payload = {
                "remediation": key,
                "host": host,
                "site": labels.get("site", ""),
                "alertname": labels.get("alertname", ""),
                "fingerprint": str(alert.get("fingerprint", ""))[:64],
                "extra_vars": extra,
            }
            ok = self.dispatch(payload)
            with self._lock:
                self.counters.dispatched[(key, "ok" if ok else "error")] += 1
            if ok:
                sent.append(payload)
        return sent


def github_dispatcher(repo: str, token: str, dry_run: bool) -> Callable[[dict[str, Any]], bool]:
    url = f"https://api.github.com/repos/{repo}/dispatches"

    def _dispatch(payload: dict[str, Any]) -> bool:
        body = json.dumps({"event_type": "remediate", "client_payload": payload}).encode()
        if dry_run:
            LOG.info("DRY_RUN dispatch: %s", body.decode())
            return True
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                ok = resp.status == 204
        except urllib.error.URLError as exc:
            LOG.error("dispatch failed: %s", exc)
            return False
        LOG.info("dispatched %s for %s", payload["remediation"], payload["host"])
        return ok

    return _dispatch


def make_handler(relay: Relay, webhook_token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            LOG.debug("%s - %s", self.address_string(), fmt % args)

        def _reply(self, status: HTTPStatus, body: str, ctype: str = "application/json") -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._reply(HTTPStatus.OK, '{"status":"ok"}')
            elif self.path == "/metrics":
                self._reply(HTTPStatus.OK, relay.counters.render(), "text/plain; version=0.0.4")
            else:
                self._reply(HTTPStatus.NOT_FOUND, '{"error":"not found"}')

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/alertmanager":
                self._reply(HTTPStatus.NOT_FOUND, '{"error":"not found"}')
                return
            expected = f"Bearer {webhook_token}".encode()
            if not webhook_token or not hmac.compare_digest(
                self.headers.get("Authorization", "").encode(), expected
            ):
                self._reply(HTTPStatus.UNAUTHORIZED, '{"error":"unauthorized"}')
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                self._reply(HTTPStatus.BAD_REQUEST, '{"error":"bad length"}')
                return
            try:
                notification = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._reply(HTTPStatus.BAD_REQUEST, '{"error":"invalid json"}')
                return
            sent = relay.handle(notification)
            self._reply(HTTPStatus.OK, json.dumps({"dispatched": len(sent)}))

    return Handler


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GITHUB_TOKEN", "")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    if not token and not dry_run:
        raise SystemExit("GITHUB_TOKEN is required unless DRY_RUN=true")
    webhook_token = os.environ["WEBHOOK_TOKEN"]
    catalog = load_catalog(os.environ.get("CATALOG_PATH", "/etc/remediator/catalog.yaml"))
    relay = Relay(catalog, github_dispatcher(repo, token, dry_run))
    port = int(os.environ.get("LISTEN_PORT", "8080"))
    LOG.info("remediator listening on :%s with %d catalog entries (dry_run=%s)", port, len(catalog), dry_run)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(relay, webhook_token)).serve_forever()


if __name__ == "__main__":
    main()

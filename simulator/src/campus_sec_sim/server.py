"""HTTP API and Prometheus endpoint (stdlib http.server, no framework)."""

from __future__ import annotations

import hmac
import json
import logging
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import __version__
from .fleet import Fleet, InvalidRequest, UnknownDevice
from .metrics import build_registry

LOG = logging.getLogger("campus_sec_sim.server")
MAX_BODY_BYTES = 4096

DEVICE_ROUTE = re.compile(r"^/api/v1/devices/([a-z]+-\d{4})$")
REBOOT_ROUTE = re.compile(r"^/api/v1/devices/([a-z]+-\d{4})/reboot$")
FIRMWARE_ROUTE = re.compile(r"^/api/v1/devices/([a-z]+-\d{4})/firmware$")


def make_handler(fleet: Fleet, api_token: str) -> type[BaseHTTPRequestHandler]:
    registry = build_registry(fleet)

    class Handler(BaseHTTPRequestHandler):
        server_version = f"campus-sec-sim/{__version__}"

        # -------------------------------------------------------------- helpers
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            LOG.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, status: HTTPStatus, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not api_token:
                return False  # mutating API disabled when no token configured
            header = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            return hmac.compare_digest(header.encode(), expected.encode())

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > MAX_BODY_BYTES:
                raise InvalidRequest("request body too large")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise InvalidRequest("body must be JSON") from exc
            if not isinstance(data, dict):
                raise InvalidRequest("body must be a JSON object")
            return data

        # ---------------------------------------------------------------- verbs
        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._send_json(HTTPStatus.OK, {"status": "ok", "version": __version__})
                return
            if path == "/metrics":
                body = generate_latest(registry)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/v1/devices":
                self._send_json(HTTPStatus.OK, {"site": fleet.config.site, "devices": fleet.snapshot()})
                return
            match = DEVICE_ROUTE.match(path)
            if match:
                try:
                    self._send_json(HTTPStatus.OK, fleet.device(match.group(1)))
                except UnknownDevice:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown device"})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if not self._authorized():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                body = self._read_json()
                match = REBOOT_ROUTE.match(path)
                if match:
                    self._send_json(HTTPStatus.ACCEPTED, fleet.reboot(match.group(1)))
                    return
                match = FIRMWARE_ROUTE.match(path)
                if match:
                    version = str(body.get("version", ""))
                    self._send_json(HTTPStatus.ACCEPTED, fleet.update_firmware(match.group(1), version))
                    return
                if path == "/api/v1/faults":
                    result = fleet.inject_fault(str(body.get("fault", "")), str(body.get("device_id", "")))
                    self._send_json(HTTPStatus.OK, result)
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except UnknownDevice:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown device"})
            except InvalidRequest as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


class SimulatorServer:
    """Owns the HTTP server and the simulation tick thread."""

    def __init__(self, fleet: Fleet, host: str, port: int, api_token: str) -> None:
        self.fleet = fleet
        self.httpd = ThreadingHTTPServer((host, port), make_handler(fleet, api_token))
        self._stop = threading.Event()
        self._ticker = threading.Thread(target=self._run_ticks, name="sim-tick", daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def _run_ticks(self) -> None:
        interval = self.fleet.config.tick_seconds
        while not self._stop.wait(interval):
            try:
                self.fleet.tick(interval)
            except Exception:  # pragma: no cover - keep the service alive
                LOG.exception("tick failed")

    def start_background(self) -> None:
        self._ticker.start()
        threading.Thread(target=self.httpd.serve_forever, name="sim-http", daemon=True).start()

    def serve_forever(self) -> None:
        self._ticker.start()
        try:
            self.httpd.serve_forever()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()

"""Entry point: python -m campus_sec_sim --config config.yaml"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from . import __version__
from .config import ConfigError, load_config
from .fleet import Fleet
from .server import SimulatorServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="campus-sec-sim", description=__doc__)
    parser.add_argument("--config", required=True, help="path to YAML config")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as exc:
        logging.error("invalid configuration: %s", exc)
        return 2

    if not config.api_token:
        logging.warning("api_token not set: mutating API endpoints are disabled")

    server = SimulatorServer(Fleet(config), config.listen_host, config.listen_port, config.api_token)

    def _graceful(signum: int, _frame: object) -> None:
        logging.info("signal %s received, shutting down", signum)
        server._stop.set()  # noqa: SLF001
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    logging.info("campus-sec-sim %s site=%s listening on %s:%s", __version__, config.site,
                 config.listen_host, config.listen_port)
    try:
        server.serve_forever()
    except SystemExit:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

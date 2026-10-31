#!/usr/bin/env python3
"""Poll a PromQL expression until it meets an expectation or times out.

Used as the health gate after deploys, between patch rings, and to confirm a
remediation actually cleared its alert.

  --expect empty      no series returned (e.g. no firing alerts for a site)
  --expect nonempty   at least one series
  --expect all-ones   at least one series and every value == 1 (e.g. up == 1)

Exit 0 when the expectation holds, 1 on timeout (last result printed).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Callable


def query(base_url: str, expr: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expr})}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    if payload.get("status") != "success":
        raise RuntimeError(f"query failed: {payload}")
    return payload["data"]["result"]


def satisfied(result: list[dict[str, Any]], expect: str) -> bool:
    if expect == "empty":
        return len(result) == 0
    if expect == "nonempty":
        return len(result) > 0
    if expect == "all-ones":
        return len(result) > 0 and all(float(s["value"][1]) == 1.0 for s in result)
    raise ValueError(expect)


def wait(fetch: Callable[[], list[dict[str, Any]]], expect: str, timeout_s: float, interval_s: float,
         stable_s: float = 0.0, clock: Callable[[], float] = time.monotonic,
         sleep: Callable[[float], None] = time.sleep) -> tuple[bool, list[dict[str, Any]]]:
    """Return (ok, last_result). With stable_s > 0 the expectation must hold that long."""
    deadline = clock() + timeout_s
    held_since: float | None = None
    last: list[dict[str, Any]] = []
    while True:
        try:
            last = fetch()
            ok = satisfied(last, expect)
        except (OSError, RuntimeError) as exc:
            print(f"query error: {exc}", file=sys.stderr)
            ok = False
        now = clock()
        if ok:
            held_since = held_since if held_since is not None else now
            if now - held_since >= stable_s:
                return True, last
        else:
            held_since = None
        if now >= deadline:
            return False, last
        sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", required=True, help="e.g. http://127.0.0.1:19090")
    parser.add_argument("--expr", required=True)
    parser.add_argument("--expect", choices=["empty", "nonempty", "all-ones"], required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--stable", type=float, default=0, help="seconds the condition must hold")
    args = parser.parse_args()

    ok, last = wait(lambda: query(args.prometheus, args.expr), args.expect,
                    args.timeout, args.interval, args.stable)
    summary = json.dumps([{"metric": s.get("metric"), "value": s.get("value", [None, None])[1]} for s in last])
    print(f"{'PASS' if ok else 'FAIL'} expect={args.expect} expr={args.expr}")
    print(f"last result: {summary}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Boot the app and prove the server actually answers requests.

The unit suite drives the page through Streamlit's AppTest, which never opens a
socket: a release whose server accepts connections but serves nothing still
passes it. This script runs the real server, waits for the health endpoint, and
exits non-zero if the app never answers.

Run it with `uv run python scripts/smoke_serve.py`.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "streamlit_app.py"

#: Generous enough for a first import on a slow runner, short enough to fail CI
#: rather than hang the job.
START_TIMEOUT = 40.0
POLL_INTERVAL = 0.25
REQUEST_TIMEOUT = 5.0


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(url: str) -> tuple[int, str]:
    """Return (status, body prefix), turning an error response into a status."""
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            return int(response.status), response.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(200).decode("utf-8", "replace")


def main() -> int:
    port = free_port()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP),
        "--server.headless",
        "true",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    ]

    # The child writes to a file, not a pipe: a full pipe would block the server
    # before it ever answered, which would look exactly like the bug we test for.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )
        health = f"http://127.0.0.1:{port}/_stcore/health"
        deadline = time.monotonic() + START_TIMEOUT
        last_error = "no request completed"
        answered = False
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    last_error = f"server exited with code {process.returncode}"
                    break
                try:
                    status, body = fetch(health)
                except (urllib.error.URLError, OSError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                else:
                    if status == 200 and body.strip() == "ok":
                        status, body = fetch(f"http://127.0.0.1:{port}/")
                        if status != 200 or not body:
                            print(
                                f"FAIL: index page returned {status} with "
                                f"{len(body)} bytes of body"
                            )
                            return 1
                        print(f"OK: server answered on 127.0.0.1:{port} (health 200, index 200)")
                        answered = True
                        return 0
                    last_error = f"health returned {status} with body {body.strip()[:60]!r}"
                time.sleep(POLL_INTERVAL)

            print(
                f"FAIL: no answer on 127.0.0.1:{port} within {START_TIMEOUT:.0f}s "
                f"(last error: {last_error})"
            )
            return 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if not answered:
                log.seek(0)
                output = log.read().strip()
                if output:
                    print("--- server output (tail) ---")
                    print(output[-2000:])


if __name__ == "__main__":
    raise SystemExit(main())

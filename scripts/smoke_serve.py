#!/usr/bin/env python3
"""Boot the app and prove the server actually answers requests.

The unit suite drives the page through Streamlit's AppTest, which never opens a
socket: a release whose server accepts connections but serves nothing still
passes it. This script runs the real server, waits for the health endpoint, and
exits non-zero if the app never answers.

Run it with `uv run python scripts/smoke_serve.py`.

Pass `--stacks` to make a failure diagnostic: the server is started through a
bootstrap that installs a `faulthandler` handler on SIGUSR1, so when it never
answers this script can ask the hung process to dump every thread's stack before
it kills it. That dump is the only reliable way to tell a blocked event loop
from a socket that is accepted and never serviced.
"""

from __future__ import annotations

import argparse
import signal
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

#: `python -m streamlit` with a stack-dump handler installed. faulthandler writes
#: from a C-level signal handler, so it can report the stacks of threads that are
#: too stuck to run Python themselves.
SERVE_WITH_STACKS = (
    "import faulthandler, runpy, signal, sys\n"
    "faulthandler.register(signal.SIGUSR1, all_threads=True)\n"
    "sys.argv = ['streamlit', *sys.argv[1:]]\n"
    "runpy.run_module('streamlit', run_name='__main__')\n"
)


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


def request_stack_dump(process: subprocess.Popen) -> None:
    """Ask a hung server to dump its threads, into the log the caller prints."""
    if process.poll() is not None:
        print("(no stack dump: the server had already exited)")
        return
    if not hasattr(signal, "SIGUSR1"):
        print("(no stack dump: SIGUSR1 does not exist on this platform)")
        return
    print(f"--- asking pid {process.pid} for thread stacks (SIGUSR1) ---")
    try:
        process.send_signal(signal.SIGUSR1)
    except OSError as exc:  # process raced us to exit
        print(f"(no stack dump: {type(exc).__name__}: {exc})")
        return
    time.sleep(1.5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stacks",
        action="store_true",
        help="on failure, dump the hung server's thread stacks before killing it",
    )
    args = parser.parse_args()

    port = free_port()
    serve_args = [
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
    if args.stacks:
        command = [sys.executable, "-c", SERVE_WITH_STACKS, *serve_args]
    else:
        command = [sys.executable, "-m", "streamlit", *serve_args]

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
            if args.stacks:
                request_stack_dump(process)
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
                    print(output[-8000:] if args.stacks else output[-2000:])


if __name__ == "__main__":
    raise SystemExit(main())

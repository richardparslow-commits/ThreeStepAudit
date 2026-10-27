# Streamlit 1.66.1 serve failure on macOS — observations

**Status: unresolved and not filed upstream.** The failure never reproduced on
demand: the same command that failed five times in a row later passed eight
consecutive times without any change. A bug report claiming reproduction would
waste maintainer time, so this records what was seen, what was ruled out, and
what to capture if it returns.

## Machine

| | |
|---|---|
| OS | macOS 27.0.1 (build 26A434), arm64, kernel 27.0.0 |
| Python | 3.14.6 (Clang 21.0.0) |
| uv | 0.13.5 |
| Streamlit | 1.66.1 affected; 1.59.0 never failed |
| Shared deps | uvicorn 0.46.0, starlette 1.3.1, websockets 16.0, anyio 4.13.0 (identical on both versions) |

## Symptom

`streamlit run streamlit_app.py --server.headless true --server.address 127.0.0.1`
prints its banner and binds the port, then every request fails:

```
2026-10-26 21:53:26.627 Uvicorn server started on 127.0.0.1:57486
… (banner) …
```

- `curl http://127.0.0.1:PORT/_stcore/health` → `http=000`
- `urllib` → `ConnectionResetError [Errno 54] Connection reset by peer`
- `nc -z 127.0.0.1 PORT` → **succeeds** (the kernel accepts the connection)
- no access log appears, even with `--logger.level debug`
- the debug log's last line is `Setting up signal handler`, after
  `Uvicorn server started` — nothing after that

`streamlit hello` (the built-in demo) served normally on 1.66.1 during the same
period, and a plain `python -m http.server` on loopback worked throughout, so
this is not a general loopback or firewall fault.

## Timeline (local, 2026-10-26)

| Time | What | Result |
|---|---|---|
| 21:34–21:39 | 1.66.1 launched various ways (default bind, IPv4 bind, `::`, concurrent instances, two-line app) | all `000`, repeated polls up to 60 s |
| 21:42 | 1.66.1 through `scripts/smoke_serve.py`, three runs | **3 pass** |
| 21:53 | 1.66.1 after a clean `uv sync --locked` (project venv) | **fail** |
| 21:54 | 1.66.1 in the project venv, three more runs | **3 fail** |
| 21:55 | 1.66.1 in a throwaway `uv run --no-project` env, two runs | **2 fail** |
| 21:56 | 1.59.0 control, same minute, same machine | **pass** |
| 22:06 | `streamlit hello` on 1.66.1 | **pass** |
| 22:07–22:15 | 1.66.1 through the smoke test (2 + 6 runs); 1.59.0 control (6 runs) | **1.66.1: 8 pass; 1.59.0: 6 pass; 0 fail** |

The failures cluster in one ~3-minute window and then stop. No code, lock, or
environment change separates the failing runs from the passing ones.

## Ruled out

- **Our app**: a two-line `st.write("hi")` app failed in the same window, and
  `streamlit hello` passed in it.
- **The project venv**: the throwaway `uv run --no-project --with streamlit==1.66.1`
  env failed too, with identical dependency versions.
- **Binding**: default `::`, explicit `127.0.0.1`, and `[::1]` all behaved the same.
- **Concurrency**: two 1.66.1 instances served fine together at 21:43.
- **Platform-wide impossibility**: CI on `ubuntu-latest` ran the same lock and
  the same smoke step green (probe branch `0ab35db`, run 40441746156, step
  "Check the server actually serves" → success; branch deleted afterwards).
- **Version determinism**: 1.66.1 passed 8 consecutive runs after the window.

So neither "1.66.1 is broken on macOS" nor "it was my app" survives the data.

## Reproducer harness

`scripts/smoke_serve.py` in this repo boots the app on a free port, polls
`/_stcore/health`, then fetches `/`, and exits non-zero with the server's output
tail on failure. It is the only thing here that exercises a real socket; the
`unittest` suite uses AppTest, which never opens one.

```
uv run python scripts/smoke_serve.py
```

## If it recurs, capture

1. `uv run python scripts/smoke_serve.py --stacks` — it starts the server with a
   `faulthandler` handler installed and, when it never answers, asks the hung
   process to dump every thread's stack before killing it. The useful question
   is whether the event loop thread is blocked, and the log alone cannot answer
   it. `sample <pid> 5` or `py-spy dump --pid <pid>` against a server you started
   yourself gives the same view.
2. The full `--logger.level debug` output, not the tail.
3. `lsof -p <pid>` — in particular whether the listening socket is paired with
   an accepted socket that never gets serviced.
4. Whether a reboot clears it, and whether it only follows a session that
   started and killed many Streamlit servers (this window followed ~10 killed
   instances, which is the only unusual condition observed).

## Current stance

The project stays on `streamlit>=1.59.0`, which has never failed here. The smoke
test gates any future bump, so a recurrence fails CI or a local run rather than
shipping an app that answers nothing.

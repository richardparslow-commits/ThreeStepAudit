# Contributing

The app is small; three commands cover almost everything you need.

## Run it

Requires [`uv`](https://docs.astral.sh/uv/).

```
$ uv sync
$ uv run streamlit run streamlit_app.py
```

Then open <http://localhost:8501>. Drafts go to a local SQLite file, so there is
nothing to configure first. CI installs with `uv sync --locked`, so if you change
`pyproject.toml`, refresh `uv.lock` with `uv lock` in the same change.

## Test it

```
$ uv run python -m unittest discover -s tests -t . -v
```

That is the command `.github/workflows/tests.yml` runs, so a green local run is
what CI checks.

## Commit with the helper

```
$ scripts/commit.sh <<'EOF'
Subject line

Body — apostrophes, $HOME, `backticks` and "quotes" all stay literal.
EOF
```

The helper reads the message from stdin and hands git a file, so nothing in it is
re-parsed as shell syntax. Keep the heredoc at the top level: on the bash 3.2
macOS ships, `git commit -m "$(cat <<'EOF' … EOF)"` fails on a single apostrophe
("visitor's") with `unexpected EOF while looking for matching '`.

Any further arguments are passed straight to `git commit`, so
`scripts/commit.sh -a <<'EOF'` stages tracked changes as well. The script refuses
an empty message, and refuses a terminal on stdin rather than silently waiting
for one.

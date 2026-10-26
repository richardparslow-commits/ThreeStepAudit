# 🔍 ThreeStepAudit

Capture an audit in three steps, then export the finished report as Markdown:

1. **Scope & criteria** — what is being audited, against which standard and
   period, and the objectives the audit has to answer.
2. **Evidence & testing** — one record per piece of evidence, each mapped to a
   step 1 objective, with a result of not tested, pass, exception or not
   applicable.
3. **Findings & conclusion** — findings traced back to the evidence that raised
   them, then the audit opinion and sign-off.

Later steps build on what earlier ones locked in: every objective needs at least
one piece of evidence, an exception has to be explained with a finding, and the
app refuses to conclude "Conforms" while a High finding is open.

Each step is saved when you submit it, and the draft reloads from the link in
your browser — bookmark that link to come back to it. "Start over" clears it.

The models, storage, report and one UI module per step live in
`three_step_audit/`; `streamlit_app.py` only wires the steps together.

### How to run it on your own machine

Prerequisite: install `uv` if you don't already have it.

```
$ curl -LsSf https://astral.sh/uv/install.sh | sh
```

1. Sync the dependencies

   ```
   $ uv sync
   ```

2. Run the app

   ```
   $ uv run streamlit run streamlit_app.py
   ```

### Committing

`scripts/commit.sh` reads the commit message from stdin and hands it to git as a
file, so nothing in the message is ever re-parsed as shell syntax:

```
$ scripts/commit.sh <<'EOF'
Subject line

Body — apostrophes, $HOME, `backticks` and "quotes" all stay literal.
EOF
```

Any further arguments are passed straight to `git commit`, so
`scripts/commit.sh -a <<'EOF'` stages tracked changes as usual. The script
refuses an empty message, and refuses a terminal on stdin rather than silently
waiting for one.

Keep the heredoc at the top level, though: `git commit -m "$(cat <<'EOF' … EOF)"`
fails on the bash 3.2 that macOS ships, because a heredoc inside `$( )` is not
treated as a message body — a single apostrophe ("visitor's") ends the command
with `unexpected EOF while looking for matching '` before git ever runs.

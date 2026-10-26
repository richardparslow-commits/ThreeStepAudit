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

### Contributing

Running the suite and committing with `scripts/commit.sh` is covered in
[CONTRIBUTING.md](CONTRIBUTING.md).

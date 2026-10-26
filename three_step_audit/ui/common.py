"""Shared Streamlit state and rendering helpers for the three-step page.

Anything more than one step needs lives here: the step names, the session-state
keys, and the widget-key, reset and error helpers. Each step's own widgets stay
in its own module so ``streamlit_app.py`` remains a thin orchestrator.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from three_step_audit.models import FieldError
from three_step_audit.workflow import Workflow

STEPS: tuple[str, ...] = ("Scope & criteria", "Evidence & testing", "Findings & conclusion")

#: Session-state keys, one namespace: the error list for each step, the stable
#: row ids for each repeating editor, and the last validated payload.
VERSION_KEY = "form_version"
SCOPE_ERRORS = "scope_errors"
EVIDENCE_ERRORS = "evidence_errors"
FINDINGS_ERRORS = "finding_errors"
ITEM_IDS = "evidence_item_ids"
ITEM_SEEDS = "evidence_item_seeds"
EVIDENCE_PLAN = "evidence_plan"
FINDING_IDS = "finding_item_ids"
FINDING_SEEDS = "finding_item_seeds"
FINDINGS_PLAN = "finding_register"


def init_session_state() -> None:
    """Seed the keys the page reads on every run."""
    st.session_state.setdefault(VERSION_KEY, 0)
    st.session_state.setdefault(SCOPE_ERRORS, [])
    st.session_state.setdefault(EVIDENCE_ERRORS, [])
    st.session_state.setdefault(FINDINGS_ERRORS, [])


def widget_key(name: str) -> str:
    """Version the widget keys so 'Start over' can reset every input at once."""
    return f"{name}::{st.session_state[VERSION_KEY]}"


def reset_draft_state() -> None:
    """Forget everything this session holds about the draft that was cleared."""
    st.session_state[SCOPE_ERRORS] = []
    st.session_state[EVIDENCE_ERRORS] = []
    st.session_state[FINDINGS_ERRORS] = []
    for key in (
        ITEM_IDS,
        ITEM_SEEDS,
        EVIDENCE_PLAN,
        FINDING_IDS,
        FINDING_SEEDS,
        FINDINGS_PLAN,
    ):
        st.session_state.pop(key, None)
    st.session_state[VERSION_KEY] += 1


def render_step_list(workflow: Workflow) -> None:
    state = [
        "saved" if workflow.scope else "in progress",
        "saved" if workflow.evidence else ("in progress" if workflow.scope else "not started"),
        "saved"
        if workflow.findings
        else ("in progress" if workflow.evidence else "not started"),
    ]

    with st.sidebar:
        st.header("Audit workflow")
        for number, (name, status) in enumerate(zip(STEPS, state, strict=True), start=1):
            if status == "in progress":
                st.markdown(f"**▶ {number}. {name}**  \n:gray[{status}]")
            elif status == "saved":
                st.markdown(f"✓ {number}. {name}  \n:gray[{status}]")
            else:
                st.markdown(f":gray[{number}. {name}  \n{status}]")


def render_errors(errors: list[FieldError], label: Callable[[str], str]) -> None:
    if not errors:
        return
    st.error(f"{len(errors)} field(s) need attention before this step can be saved.")
    for error in errors:
        st.markdown(f"- **{label(error.field)}** — {error.message}")

"""ThreeStepAudit — capture an audit in three steps: scope, evidence, findings.

This page only wires the steps together: it loads the visitor's draft, decides
which step is available, and hands each one to its renderer in
``three_step_audit.ui``. The step screens themselves live one-per-module.
"""

from __future__ import annotations

import re
from uuid import uuid4

import streamlit as st

from three_step_audit.storage import DraftStore, DraftStoreError
from three_step_audit.ui import (
    init_session_state,
    render_errors,
    render_evidence_section,
    render_export,
    render_findings_section,
    render_saved,
    render_scope_form,
    render_step_list,
    scope_label,
)
from three_step_audit.ui.common import SCOPE_ERRORS
from three_step_audit.workflow import Workflow

#: Drafts are addressed by an unguessable id carried in the visitor's URL, which
#: is what keeps one visitor's audit out of another's way without sign-in.
DRAFT_PARAM = "draft"
DRAFT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


@st.cache_resource
def get_store() -> DraftStore:
    return DraftStore()


def visitor_draft_id() -> str:
    """This browser tab's draft id, minting and storing one on first visit."""
    candidate = st.query_params.get(DRAFT_PARAM)
    if isinstance(candidate, list):
        candidate = candidate[0] if candidate else None
    if isinstance(candidate, str) and DRAFT_ID_PATTERN.fullmatch(candidate):
        return candidate
    draft_id = uuid4().hex
    st.query_params[DRAFT_PARAM] = draft_id
    return draft_id


st.set_page_config(page_title="ThreeStepAudit", page_icon="🔍", layout="centered")
init_session_state()

draft_id = visitor_draft_id()
store = get_store()
workflow = Workflow()
stored_at = None
try:
    workflow = store.load_for_visitor(draft_id) or Workflow()
    if workflow.scope is not None:
        stored_at = store.saved_at(draft_id)
except ValueError as exc:
    st.warning(f"The saved draft is unreadable and was not loaded ({exc}). Saving replaces it.")
except DraftStoreError as exc:
    st.warning(f"Draft storage is unavailable, so nothing can be saved this session ({exc}).")

render_step_list(workflow)
st.title("ThreeStepAudit")
st.caption("Step 1 of 3 — scope & criteria")
st.write(
    "Define what is being audited and against which criteria. Everything captured here "
    "becomes the frame for evidence collection in step 2."
)

# Reserve the slot above the form, then fill it once this run has validated.
error_slot = st.container()
saved_scope = render_scope_form(workflow.scope)
with error_slot:
    render_errors(st.session_state[SCOPE_ERRORS], scope_label)

if saved_scope is not None:
    try:
        stored_at = store.save(
            draft_id,
            Workflow(scope=saved_scope, evidence=workflow.evidence, findings=workflow.findings),
        )
    except DraftStoreError as exc:
        st.error(f"Could not save the draft: {exc}")
        stored_at = None
    else:
        workflow = Workflow(
            scope=saved_scope, evidence=workflow.evidence, findings=workflow.findings
        )
        st.success("Step 1 saved.")

if workflow.scope is None:
    st.divider()
    st.subheader("Step 2 — evidence & testing")
    st.info("Save step 1 first: step 2 tests the objectives you define there.")
else:
    render_saved(workflow, stored_at, draft_id, store)
    workflow = render_evidence_section(workflow, store, draft_id)
    if workflow.evidence is None:
        st.divider()
        st.subheader("Step 3 — findings & conclusion")
        st.info("Save step 2 first: findings are raised against the evidence you record.")
    else:
        workflow = render_findings_section(workflow, store, draft_id)
    render_export(workflow)

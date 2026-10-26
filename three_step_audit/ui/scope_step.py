"""Step 1 — scope & criteria: the engagement form and the saved-draft summary."""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from three_step_audit.models import (
    AUDIT_TYPES,
    SCOPE_AREAS,
    STANDARDS,
    AuditScope,
    parse_lines,
)
from three_step_audit.storage import DraftStore, DraftStoreError
from three_step_audit.ui.common import SCOPE_ERRORS, reset_draft_state, widget_key
from three_step_audit.workflow import Workflow

SCOPE_LABELS: dict[str, str] = {
    "title": "Audit title",
    "organization": "Organization",
    "audit_type": "Audit type",
    "standard": "Criteria / standard",
    "custom_standard": "Named criteria",
    "period_start": "Period start",
    "period_end": "Period end",
    "lead_auditor": "Lead auditor",
    "scope_summary": "Scope description",
    "in_scope_areas": "In-scope areas",
    "objectives": "Objectives",
    "exclusions": "Exclusions",
}


def scope_label(field: str) -> str:
    return SCOPE_LABELS.get(field, field)


def render_scope_form(prefill: AuditScope | None) -> AuditScope | None:
    """Draw the step 1 form; return a validated scope when this run submitted one."""
    today = date.today()
    default_start = date(today.year, 1, 1)
    if default_start > today:
        default_start = today

    def index_of(options: tuple[str, ...], value: str) -> int:
        return options.index(value) if value in options else 0

    with st.form("scope_form"):
        st.subheader("Engagement")
        title = st.text_input(
            "Audit title",
            value=prefill.title if prefill else "",
            key=widget_key("title"),
            placeholder="e.g. FY26 access-control review",
        )
        organization = st.text_input(
            "Organization or entity audited",
            value=prefill.organization if prefill else "",
            key=widget_key("organization"),
        )

        left, right = st.columns(2)
        audit_type = left.selectbox(
            "Audit type",
            AUDIT_TYPES,
            index=index_of(AUDIT_TYPES, prefill.audit_type) if prefill else 0,
            key=widget_key("audit_type"),
        )
        standard = right.selectbox(
            "Criteria / standard",
            STANDARDS,
            index=index_of(STANDARDS, prefill.standard) if prefill else 0,
            key=widget_key("standard"),
        )
        custom_standard = st.text_input(
            "Named criteria",
            value=prefill.custom_standard if prefill else "",
            key=widget_key("custom_standard"),
            help="Only required when the criteria is “Other”.",
            placeholder="e.g. Supplier code of conduct v4",
        )

        dates = st.columns(2)
        period_start = dates[0].date_input(
            "Period start",
            value=(prefill.period_start if prefill and prefill.period_start else default_start),
            key=widget_key("period_start"),
            max_value=today,
        )
        period_end = dates[1].date_input(
            "Period end",
            value=(prefill.period_end if prefill and prefill.period_end else today),
            key=widget_key("period_end"),
            max_value=today,
        )
        lead_auditor = st.text_input(
            "Lead auditor",
            value=prefill.lead_auditor if prefill else "",
            key=widget_key("lead_auditor"),
        )

        st.subheader("Scope")
        scope_summary = st.text_area(
            "Scope description",
            value=prefill.scope_summary if prefill else "",
            key=widget_key("scope_summary"),
            height=120,
            placeholder="What the audit covers, for whom, and why now.",
        )
        areas = st.multiselect(
            "In-scope areas",
            SCOPE_AREAS,
            default=list(prefill.in_scope_areas) if prefill else [],
            key=widget_key("in_scope_areas"),
        )
        exclusions = st.text_area(
            "Exclusions (optional)",
            value=prefill.exclusions if prefill else "",
            key=widget_key("exclusions"),
            height=80,
            placeholder="Anything explicitly out of scope.",
        )
        objectives_text = st.text_area(
            "Objectives — one per line",
            value="\n".join(prefill.objectives) if prefill else "",
            key=widget_key("objectives"),
            height=110,
            placeholder="Confirm access reviews happen quarterly\nVerify leavers lose access within 24h",
        )

        submitted = st.form_submit_button("Save step 1", type="primary")

    if not submitted:
        return None

    scope = AuditScope(
        title=title,
        organization=organization,
        audit_type=audit_type,
        standard=standard,
        period_start=period_start,
        period_end=period_end,
        lead_auditor=lead_auditor,
        scope_summary=scope_summary,
        in_scope_areas=list(areas),
        objectives=parse_lines(objectives_text),
        exclusions=exclusions,
        custom_standard=custom_standard,
    )
    errors = scope.validate()
    st.session_state[SCOPE_ERRORS] = errors
    return None if errors else scope


def render_saved(
    workflow: Workflow,
    saved_at: datetime | None,
    draft_id: str,
    store: DraftStore,
) -> None:
    scope = workflow.scope
    if scope is None:
        return
    st.subheader("Saved draft")
    st.markdown(
        f"**{scope.title}** · {scope.organization}  \n"
        f"{scope.audit_type} audit · {scope.criteria()} · {scope.period_label()}  \n"
        f"{len(scope.in_scope_areas)} area(s) in scope · {len(scope.objectives)} objective(s)"
    )
    if saved_at is not None:
        st.caption(
            f"Last saved {saved_at:%Y-%m-%d %H:%M} UTC — this draft reloads after a "
            "refresh or restart."
        )
    st.caption(
        f"Draft {draft_id[:8]} belongs to this browser link. Bookmark the page to come "
        "back to it; anyone with the link can edit it."
    )
    if st.button("Start over"):
        try:
            store.clear(draft_id)
        except DraftStoreError as exc:
            st.error(f"Could not clear the saved draft: {exc}")
            return
        reset_draft_state()
        st.rerun()

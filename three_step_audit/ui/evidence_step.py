"""Step 2 — evidence & testing: one editor per evidence item, tested against step 1."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st

from three_step_audit.evidence import TEST_RESULTS, EvidenceItem, EvidencePlan
from three_step_audit.models import AuditScope
from three_step_audit.storage import DraftStore, DraftStoreError
from three_step_audit.ui.common import (
    EVIDENCE_ERRORS,
    EVIDENCE_PLAN,
    ITEM_IDS,
    ITEM_SEEDS,
    render_errors,
    widget_key,
)
from three_step_audit.workflow import Workflow

EVIDENCE_LABELS: dict[str, str] = {
    "methodology": "Methodology",
    "items": "Evidence",
    "reference": "Reference",
    "description": "What the evidence shows",
    "source": "Source",
    "objective": "Objective",
    "collected_on": "Collected on",
    "result": "Result",
    "notes": "Notes",
}


def evidence_label(field: str) -> str:
    if field.startswith("items."):
        parts = field.split(".")
        if len(parts) == 3 and parts[1].isdigit():
            return f"Evidence {int(parts[1]) + 1} · {EVIDENCE_LABELS.get(parts[2], parts[2])}"
        return EVIDENCE_LABELS["items"]
    return EVIDENCE_LABELS.get(field, field)


def seed_evidence_items(plan: EvidencePlan | None) -> None:
    """Give each evidence row a stable id so removing one cannot shuffle the rest."""
    if ITEM_IDS in st.session_state:
        return
    seeds = plan.items if plan else [EvidenceItem()]
    ids = [uuid4().hex for _ in seeds]
    st.session_state[ITEM_IDS] = ids
    st.session_state[ITEM_SEEDS] = dict(zip(ids, seeds, strict=True))


def evidence_widget_key(item_id: str, field: str) -> str:
    return f"ev_{item_id}_{field}"


def render_evidence_item(scope: AuditScope, number: int, item_id: str) -> None:
    seed: EvidenceItem | None = st.session_state[ITEM_SEEDS].get(item_id)
    objectives = list(scope.objectives)
    if seed and seed.objective and seed.objective not in objectives:
        # Keep a now-unknown objective selectable so it is flagged, not silently reassigned.
        objectives = [seed.objective, *objectives]

    with st.container(border=True):
        st.markdown(f"**Evidence {number}**")
        row = st.columns([1, 2])
        row[0].text_input(
            "Reference",
            value=seed.reference if seed else "",
            key=evidence_widget_key(item_id, "reference"),
            placeholder="AC-01",
        )
        row[1].selectbox(
            "Objective",
            objectives,
            index=objectives.index(seed.objective) if seed and seed.objective in objectives else 0,
            key=evidence_widget_key(item_id, "objective"),
        )
        st.text_area(
            "What the evidence shows",
            value=seed.description if seed else "",
            key=evidence_widget_key(item_id, "description"),
            height=80,
            placeholder="Quarterly access review completed for all 12 production systems.",
        )
        row = st.columns(2)
        row[0].text_input(
            "Source",
            value=seed.source if seed else "",
            key=evidence_widget_key(item_id, "source"),
            placeholder="Identity team / review log",
        )
        row[1].date_input(
            "Collected on",
            value=(seed.collected_on if seed and seed.collected_on else date.today()),
            max_value=date.today(),
            key=evidence_widget_key(item_id, "collected_on"),
        )
        row = st.columns(2)
        row[0].selectbox(
            "Result",
            TEST_RESULTS,
            index=TEST_RESULTS.index(seed.result) if seed and seed.result in TEST_RESULTS else 0,
            key=evidence_widget_key(item_id, "result"),
        )
        row[1].text_area(
            "Notes (required for an exception)",
            value=seed.notes if seed else "",
            key=evidence_widget_key(item_id, "notes"),
            height=80,
        )
        if st.button("Remove this evidence", key=f"remove_{item_id}"):
            st.session_state[ITEM_IDS].remove(item_id)
            st.session_state[ITEM_SEEDS].pop(item_id, None)
            for field in EVIDENCE_LABELS:
                st.session_state.pop(evidence_widget_key(item_id, field), None)
            st.rerun()


def collect_evidence_plan() -> EvidencePlan:
    items = []
    for item_id in st.session_state[ITEM_IDS]:
        items.append(
            EvidenceItem(
                reference=st.session_state.get(evidence_widget_key(item_id, "reference"), ""),
                description=st.session_state.get(evidence_widget_key(item_id, "description"), ""),
                source=st.session_state.get(evidence_widget_key(item_id, "source"), ""),
                objective=st.session_state.get(evidence_widget_key(item_id, "objective"), ""),
                collected_on=st.session_state.get(evidence_widget_key(item_id, "collected_on")),
                result=st.session_state.get(
                    evidence_widget_key(item_id, "result"), TEST_RESULTS[0]
                ),
                notes=st.session_state.get(evidence_widget_key(item_id, "notes"), ""),
            )
        )
    methodology = st.session_state.get(widget_key("methodology"), "")
    return EvidencePlan(methodology=methodology, items=items)


def render_evidence_section(workflow: Workflow, store: DraftStore, draft_id: str) -> Workflow:
    """Step 2: test the step 1 objectives against collected evidence."""
    scope = workflow.scope
    if scope is None:
        return workflow
    st.divider()
    st.subheader("Step 2 — evidence & testing")
    st.caption(
        "Record what you tested for each objective in step 1. Every objective needs at least "
        "one piece of evidence before this step can be saved."
    )

    error_slot = st.container()
    seed_evidence_items(workflow.evidence)

    st.text_area(
        "Methodology",
        value=workflow.evidence.methodology if workflow.evidence else "",
        key=widget_key("methodology"),
        height=100,
        placeholder="Sampled 12 of 12 production systems, walked through two quarterly reviews, "
        "and re-performed one leavers check.",
    )

    for number, item_id in enumerate(list(st.session_state[ITEM_IDS]), start=1):
        render_evidence_item(scope, number, item_id)

    if st.button("Add evidence item"):
        item_id = uuid4().hex
        st.session_state[ITEM_IDS].append(item_id)
        st.rerun()

    just_saved = False
    if st.button("Save step 2", type="primary"):
        plan = collect_evidence_plan()
        errors = plan.validate(scope)
        st.session_state[EVIDENCE_ERRORS] = errors
        if not errors:
            try:
                workflow.evidence = plan
                store.save(draft_id, workflow)
            except DraftStoreError as exc:
                st.error(f"Could not save step 2: {exc}")
            else:
                st.session_state[EVIDENCE_PLAN] = plan
                just_saved = True

    with error_slot:
        render_errors(st.session_state[EVIDENCE_ERRORS], evidence_label)

    plan = st.session_state.get(EVIDENCE_PLAN) or workflow.evidence
    if plan is not None and not st.session_state[EVIDENCE_ERRORS]:
        totals = plan.summary(scope)
        if just_saved:
            st.success("Step 2 saved.")
        st.caption(
            f"{totals['items']} evidence item(s) · "
            f"{totals['objectives_covered']}/{totals['objectives_total']} objectives covered · "
            + ", ".join(
                f"{name} {count}" for name, count in totals["results"].items() if count
            )
        )
    return workflow

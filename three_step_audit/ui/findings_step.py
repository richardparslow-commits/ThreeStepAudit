"""Step 3 — findings & conclusion: raise findings against evidence, record the opinion."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import streamlit as st

from three_step_audit.evidence import EvidencePlan
from three_step_audit.findings import (
    FINDING_STATUSES,
    OPINIONS,
    SEVERITIES,
    Conclusion,
    Finding,
    FindingRegister,
)
from three_step_audit.models import AuditScope
from three_step_audit.storage import DraftStore, DraftStoreError
from three_step_audit.ui.common import (
    FINDINGS_ERRORS,
    FINDINGS_PLAN,
    FINDING_IDS,
    FINDING_SEEDS,
    render_errors,
    widget_key,
)
from three_step_audit.workflow import Workflow

FINDING_LABELS: dict[str, str] = {
    "findings": "Findings",
    "reference": "Reference",
    "title": "Title",
    "severity": "Severity",
    "objective": "Objective",
    "evidence_reference": "Evidence reference",
    "condition": "What was found",
    "recommendation": "Recommendation",
    "owner": "Owner",
    "due_on": "Due on",
    "status": "Status",
    "conclusion": "Conclusion",
    "opinion": "Opinion",
    "summary": "Summary",
    "concluded_by": "Concluded by",
    "concluded_on": "Concluded on",
}


def finding_label(field: str) -> str:
    if field.startswith("findings."):
        parts = field.split(".")
        if len(parts) == 3 and parts[1].isdigit():
            return f"Finding {int(parts[1]) + 1} · {FINDING_LABELS.get(parts[2], parts[2])}"
        return FINDING_LABELS["findings"]
    if field.startswith("conclusion."):
        child = field.split(".", 1)[1]
        return f"Conclusion · {FINDING_LABELS.get(child, child)}"
    return FINDING_LABELS.get(field, field)


def seed_finding_items(register: FindingRegister | None) -> None:
    if FINDING_IDS in st.session_state:
        return
    seeds = register.findings if register and register.findings else [Finding()]
    ids = [uuid4().hex for _ in seeds]
    st.session_state[FINDING_IDS] = ids
    st.session_state[FINDING_SEEDS] = dict(zip(ids, seeds, strict=True))


def finding_widget_key(item_id: str, field: str) -> str:
    return f"fn_{item_id}_{field}"


def render_finding_item(
    scope: AuditScope, evidence: EvidencePlan, number: int, item_id: str
) -> None:
    seed: Finding | None = st.session_state[FINDING_SEEDS].get(item_id)
    objectives = list(scope.objectives)
    if seed and seed.objective and seed.objective not in objectives:
        objectives = [seed.objective, *objectives]
    references = [item.reference for item in evidence.items]
    if seed and seed.evidence_reference and seed.evidence_reference not in references:
        references = [seed.evidence_reference, *references]

    with st.container(border=True):
        st.markdown(f"**Finding {number}**")
        row = st.columns([1, 3])
        row[0].text_input(
            "Reference",
            value=seed.reference if seed else "",
            key=finding_widget_key(item_id, "reference"),
            placeholder="F-01",
        )
        row[1].text_input(
            "Title",
            value=seed.title if seed else "",
            key=finding_widget_key(item_id, "title"),
        )
        row = st.columns(2)
        row[0].selectbox(
            "Severity",
            SEVERITIES,
            index=SEVERITIES.index(seed.severity) if seed and seed.severity in SEVERITIES else 1,
            key=finding_widget_key(item_id, "severity"),
        )
        row[1].selectbox(
            "Status",
            FINDING_STATUSES,
            index=(
                FINDING_STATUSES.index(seed.status)
                if seed and seed.status in FINDING_STATUSES
                else 0
            ),
            key=finding_widget_key(item_id, "status"),
        )
        row = st.columns(2)
        row[0].selectbox(
            "Objective",
            objectives,
            index=objectives.index(seed.objective) if seed and seed.objective in objectives else 0,
            key=finding_widget_key(item_id, "objective"),
        )
        row[1].selectbox(
            "Evidence reference",
            references,
            index=(
                references.index(seed.evidence_reference)
                if seed and seed.evidence_reference in references
                else 0
            ),
            key=finding_widget_key(item_id, "evidence_reference"),
        )
        st.text_area(
            "What was found",
            value=seed.condition if seed else "",
            key=finding_widget_key(item_id, "condition"),
            height=90,
        )
        st.text_area(
            "Recommendation",
            value=seed.recommendation if seed else "",
            key=finding_widget_key(item_id, "recommendation"),
            height=90,
        )
        row = st.columns(2)
        row[0].text_input(
            "Owner",
            value=seed.owner if seed else "",
            key=finding_widget_key(item_id, "owner"),
        )
        row[1].date_input(
            "Due on",
            value=seed.due_on if seed and seed.due_on else date.today(),
            key=finding_widget_key(item_id, "due_on"),
        )
        if st.button("Remove this finding", key=f"remove_finding_{item_id}"):
            st.session_state[FINDING_IDS].remove(item_id)
            st.session_state[FINDING_SEEDS].pop(item_id, None)
            for field in FINDING_LABELS:
                st.session_state.pop(finding_widget_key(item_id, field), None)
            st.rerun()


def collect_register() -> FindingRegister:
    findings = []
    for item_id in st.session_state[FINDING_IDS]:
        findings.append(
            Finding(
                reference=st.session_state.get(finding_widget_key(item_id, "reference"), ""),
                title=st.session_state.get(finding_widget_key(item_id, "title"), ""),
                severity=st.session_state.get(
                    finding_widget_key(item_id, "severity"), SEVERITIES[1]
                ),
                objective=st.session_state.get(finding_widget_key(item_id, "objective"), ""),
                evidence_reference=st.session_state.get(
                    finding_widget_key(item_id, "evidence_reference"), ""
                ),
                condition=st.session_state.get(finding_widget_key(item_id, "condition"), ""),
                recommendation=st.session_state.get(
                    finding_widget_key(item_id, "recommendation"), ""
                ),
                owner=st.session_state.get(finding_widget_key(item_id, "owner"), ""),
                due_on=st.session_state.get(finding_widget_key(item_id, "due_on")),
                status=st.session_state.get(
                    finding_widget_key(item_id, "status"), FINDING_STATUSES[0]
                ),
            )
        )
    conclusion = Conclusion(
        opinion=st.session_state.get(widget_key("opinion"), OPINIONS[-1]),
        summary=st.session_state.get(widget_key("conclusion_summary"), ""),
        concluded_by=st.session_state.get(widget_key("concluded_by"), ""),
        concluded_on=st.session_state.get(widget_key("concluded_on")),
    )
    return FindingRegister(findings=findings, conclusion=conclusion)


def render_findings_section(workflow: Workflow, store: DraftStore, draft_id: str) -> Workflow:
    """Step 3: raise findings against the evidence, then record the opinion."""
    scope, evidence = workflow.scope, workflow.evidence
    if scope is None or evidence is None:
        return workflow

    st.divider()
    st.subheader("Step 3 — findings & conclusion")
    st.caption(
        "Raise findings against the evidence collected in step 2, then record the audit opinion. "
        "Every evidence item marked as an exception needs a finding."
    )

    error_slot = st.container()
    seed_finding_items(workflow.findings)

    for number, item_id in enumerate(list(st.session_state[FINDING_IDS]), start=1):
        render_finding_item(scope, evidence, number, item_id)

    if st.button("Add finding"):
        st.session_state[FINDING_IDS].append(uuid4().hex)
        st.rerun()

    st.markdown("**Conclusion**")
    conclusion = workflow.findings.conclusion if workflow.findings else Conclusion()
    st.selectbox(
        "Opinion",
        OPINIONS,
        index=OPINIONS.index(conclusion.opinion) if conclusion.opinion in OPINIONS else len(OPINIONS) - 1,
        key=widget_key("opinion"),
    )
    st.text_area(
        "Conclusion summary",
        value=conclusion.summary,
        key=widget_key("conclusion_summary"),
        height=100,
    )
    row = st.columns(2)
    row[0].text_input(
        "Concluded by",
        value=conclusion.concluded_by,
        key=widget_key("concluded_by"),
    )
    row[1].date_input(
        "Concluded on",
        value=conclusion.concluded_on or date.today(),
        max_value=date.today(),
        key=widget_key("concluded_on"),
    )

    just_saved = False
    if st.button("Save step 3", type="primary"):
        register = collect_register()
        errors = register.validate(scope, evidence)
        st.session_state[FINDINGS_ERRORS] = errors
        if not errors:
            try:
                workflow.findings = register
                store.save(draft_id, workflow)
            except DraftStoreError as exc:
                st.error(f"Could not save step 3: {exc}")
            else:
                st.session_state[FINDINGS_PLAN] = register
                just_saved = True

    with error_slot:
        render_errors(st.session_state[FINDINGS_ERRORS], finding_label)

    register = st.session_state.get(FINDINGS_PLAN) or workflow.findings
    if register is not None and not st.session_state[FINDINGS_ERRORS]:
        totals = register.summary()
        if just_saved:
            st.success("Step 3 saved — the audit is complete.")
        severities = ", ".join(f"{name} {count}" for name, count in totals["by_severity"].items() if count)
        st.caption(
            f"{totals['findings']} finding(s) · {totals['open_high']} open High · "
            f"opinion: {register.conclusion.opinion}" + (f" · {severities}" if severities else "")
        )
    return workflow

"""Export: the rendered audit report, its draft JSON, and an in-page preview."""

from __future__ import annotations

import streamlit as st

from three_step_audit.report import render_markdown
from three_step_audit.workflow import Workflow


def render_export(workflow: Workflow) -> None:
    if workflow.scope is None:
        return
    st.divider()
    st.subheader("Export")
    try:
        report = render_markdown(workflow)
    except ValueError as exc:
        st.warning(f"The report cannot be rendered yet ({exc}).")
        return
    st.download_button(
        "Download audit report (Markdown)",
        data=report,
        file_name=f"{workflow.file_stem()}-report.md",
        mime="text/markdown",
    )
    st.download_button(
        "Download draft (JSON)",
        data=workflow.to_json(),
        file_name=f"{workflow.file_stem()}-audit.json",
        mime="application/json",
    )
    with st.expander("Preview report"):
        st.markdown(report)

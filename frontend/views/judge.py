"""
Isolated layout interface rendering the LLM evaluation pipelines.
"""

from typing import cast

import streamlit as st

from frontend.client import fetch_all_historical_tasks
from frontend.components.results import render_trust_audit_ledger
from frontend.services import send_audit_request

__all__ = ["render_judge_tab_view"]


def _get_currently_active_task(
    historical_tasks: list[dict[str, object]], task_id: str | None
) -> dict[str, object] | None:
    """
    Finds the active task matches from historical records.
    """
    if not task_id:
        return None

    valid_tasks = [
        task
        for task in historical_tasks
        if task.get("status") == "COMPLETED" and task.get("report") is not None
    ]

    matching = [
        task for task in valid_tasks if str(task.get("task_id")) == str(task_id)
    ]
    if not matching:
        return None

    return matching[0]


def _trigger_stability_test(
    task_id: str,
    active_task_data: dict[str, object],
    chosen_engine: str,
    judge_iterations: int,
) -> None:
    """
    Sets up the evaluation arguments and triggers rerun.
    """
    report_data = active_task_data.get("report") or {}
    extracted_answers_dict = {}

    if isinstance(report_data, dict):
        extracted_answers_dict = report_data.get("extracted_answers", {})

    with st.spinner("Running AI Judge evaluation..."):
        metrics = send_audit_request(
            chosen_engine=chosen_engine,
            answers=cast(dict[str, str], extracted_answers_dict),
            judge_iterations=judge_iterations,
            source_context=cast(str, active_task_data.get("source_context", "")),
        )

    if metrics:
        st.session_state.audit_metrics = metrics
        historical_audits = st.session_state.get("historical_audits")
        if not isinstance(historical_audits, dict):
            historical_audits = {}
        historical_audits[task_id] = metrics
        st.session_state.historical_audits = historical_audits

    st.rerun()


def _render_audit_results(audit_metrics: dict[str, object] | None) -> None:
    """
    Renders metrics/results of the completed evaluation.
    """
    if not audit_metrics:
        return
    st.markdown("---")
    st.success("Audit complete!")

    metadata = cast(dict[str, object], audit_metrics.get("metadata", {}))
    kappa_score = cast(
        float,
        metadata.get("global_gwet_ac1") or metadata.get("global_gwets_ac1", 0.0),
    )

    st.metric("Agreement score (Gwet's AC1)", f"{kappa_score:.3f}")
    st.dataframe(
        cast(list[object], audit_metrics.get("item_level_stability_metrics", [])),
        use_container_width=True,
    )


def render_judge_tab_view(*, disabled: bool, models: list[str]) -> None:
    """
    Renders the isolated evaluation workspace.
    """
    st.header("LLM Judge: Evaluate Historical Extraction")
    st.markdown(
        "Quantify the extraction accuracy of a past run against its "
        "original source context."
    )

    historical_tasks: list[dict[str, object]] = fetch_all_historical_tasks()
    currently_selected_task_id: str | None = st.session_state.get("current_task_id")
    currently_active_task_data = _get_currently_active_task(
        historical_tasks, currently_selected_task_id
    )

    if not currently_active_task_data:
        st.info(
            "Please upload files under the 'Document Generator' tab or "
            "select a past run from the sidebar to evaluate."
        )
        return

    active_run_custom_name = (
        currently_active_task_data.get("custom_name") or "Unnamed Run"
    )
    st.success(
        "Evaluating Active Run: "
        f"**{active_run_custom_name}** (ID: `{str(currently_selected_task_id)[:8]}`)"
    )

    chosen_engine: str = st.selectbox(
        "Select Evaluating AI Judge", models, disabled=disabled
    )

    judge_iterations: int = st.slider(
        "Testing Iterations (Higher = more accurate but much slower!)",
        min_value=2,
        max_value=10,
        value=3,
        disabled=disabled,
    )

    st.markdown("#### Original Source Documents Under Review")
    render_trust_audit_ledger(
        source_context=cast(
            str | None, currently_active_task_data.get("source_context")
        )
    )

    if st.button("Run Stability Test", type="primary", disabled=disabled):
        _trigger_stability_test(
            cast(str, currently_selected_task_id),
            currently_active_task_data,
            chosen_engine,
            judge_iterations,
        )

    audit_metrics = cast(
        dict[str, object] | None, st.session_state.get("audit_metrics")
    )
    _render_audit_results(audit_metrics)

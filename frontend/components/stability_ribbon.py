"""
Inline analytical alert ribbon and advanced judge panels.
"""

from typing import cast

import streamlit as st

from frontend.config import MODEL_CONFIGURATIONS


def trigger_stability_test(
    task_id: str,
    active_task_data: dict[str, object],
    chosen_engine: str,
    judge_iterations: int,
) -> None:
    """Sets session state to trigger the stability test background job."""
    report_data = active_task_data.get("report")
    if not isinstance(report_data, dict):
        report_data = {}

    extracted_answers = report_data.get("extracted_answers")
    if not isinstance(extracted_answers, dict):
        extracted_answers = {}

    source_context = active_task_data.get("source_context")
    if not isinstance(source_context, str):
        source_context = ""

    st.session_state.is_processing = True
    st.session_state.job_running = True
    st.session_state.run_state = "triggered"
    st.session_state.pending_audit = {
        "task_id": task_id,
        "chosen_engine": chosen_engine,
        "judge_iterations": judge_iterations,
        "answers": extracted_answers,
        "source_context": source_context,
    }
    st.rerun()


def render_ribbon_indicator(task_id: str) -> None:
    """Helper to render Gwet's AC1 alert ribbon."""
    audit_metrics = st.session_state.get("audit_metrics")
    if not isinstance(audit_metrics, dict):
        return

    metadata = cast(dict[str, object], audit_metrics.get("metadata", {}))
    meta_task_id = metadata.get("task_id")
    payload_task_id = audit_metrics.get("task_id") or meta_task_id
    if str(payload_task_id) != str(task_id):
        return

    kappa_score = cast(

        float,
        metadata.get("global_gwet_ac1") or metadata.get("global_gwets_ac1", 0.0),
    )

    is_low_stability = kappa_score < 0.70
    if is_low_stability:
        st.warning("Low Stability Detected...")
        return

    st.success("Consensus Stability Meets Threshold")


def render_judge_settings_expander(
    *,
    task_id: str,
    active_task_data: dict[str, object],
    models: list[str],
    disabled: bool,
) -> None:
    """Renders the settings and action button inside the expander."""
    is_processing: bool = st.session_state.get("is_processing", False)

    chosen_engine = st.selectbox(
        "Select Evaluating AI Judge",
        models,
        disabled=is_processing,
        key=f"judge_engine_{task_id}",
    )
    judge_iterations = st.slider(
        "Testing Iterations (Higher = more accurate but much slower!)",
        min_value=2,
        max_value=10,
        value=3,
        disabled=is_processing,
        key=f"judge_iter_{task_id}",
    )

    run_clicked = st.button(
        "Run Stability Test",
        type="primary",
        disabled=is_processing,
        key=f"run_stability_{task_id}",
    )

    if run_clicked:
        trigger_stability_test(
            task_id,
            active_task_data,
            chosen_engine,
            judge_iterations,
        )


def render_stability_ribbon(
    *,
    task_id: str,
    active_task_data: dict[str, object],
    disabled: bool = False,
) -> None:
    """
    Renders the analytical alert ribbon and advanced LLM judge configuration.
    """
    if not active_task_data:
        return

    render_ribbon_indicator(task_id)

    models = list(MODEL_CONFIGURATIONS.keys())
    with st.expander("Advanced LLM Judge Settings", expanded=False):
        render_judge_settings_expander(
            task_id=task_id,
            active_task_data=active_task_data,
            models=models,
            disabled=disabled,
        )

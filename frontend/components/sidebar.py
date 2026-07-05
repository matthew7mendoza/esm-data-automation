"""
Handles historical states and user settings sidebar rendering
"""

import logging
from typing import Final, cast

import requests
import streamlit as st

from frontend.config import BACKEND_URL

__all__ = ["render_historical_sidebar"]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def _fetch_task_profile(task_id: str) -> dict[str, object] | None:
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
        if response.status_code == 200:
            return cast(dict[str, object], response.json())
        st.error("Failed to extract full analysis data from backend")
    except requests.exceptions.RequestException as network_transport_fault:
        logger.error(
            "Network communication loss when trying to read historical data.",
            exc_info=True,
        )
        st.error(
            "Network error trying to fetch historical profile: "
            f"{network_transport_fault}"
        )
    return None


def _update_session_state_with_task(
    task_id: str, job_details_payload: dict[str, object]
) -> None:
    st.session_state.current_task_id = task_id
    st.session_state.generator_report = job_details_payload.get("report")
    st.session_state.source_context = job_details_payload.get("source_context")
    st.session_state.current_task_custom_name = job_details_payload.get("custom_name")

    historical_audit_records = st.session_state.get("historical_audits")
    if not isinstance(historical_audit_records, dict):
        st.session_state.audit_metrics = None
        return

    st.session_state.audit_metrics = historical_audit_records.get(task_id)


def _purge_active_view() -> None:
    active_view_session_keys: list[str] = [
        "generator_report",
        "source_context",
        "audit_metrics",
        "current_task_id",
        "current_task_custom_name",
    ]
    for key_to_purge in active_view_session_keys:
        st.session_state.pop(key_to_purge, None)


def _resolve_selected_task_id(run_name: str) -> str | None:
    if run_name == "-- Create New Run --":
        _purge_active_view()
        return None

    task_id_mapping = st.session_state.get("task_mapping")
    if not isinstance(task_id_mapping, dict):
        return None

    selected_job_data = task_id_mapping.get(run_name)
    if not isinstance(selected_job_data, dict):
        return None

    return cast(str | None, selected_job_data.get("task_id"))


def _on_history_change() -> None:
    """
    Handles transition of historical task selection to keep the UI clean.
    """
    currently_selected_historical_run: str | None = st.session_state.get(
        "history_selectbox"
    )
    if not currently_selected_historical_run:
        return

    task_id = _resolve_selected_task_id(currently_selected_historical_run)
    if not task_id:
        return

    job_details_payload = _fetch_task_profile(task_id)
    if job_details_payload is not None:
        _update_session_state_with_task(task_id, job_details_payload)


def _fetch_past_tasks_raw() -> list[dict[str, object]] | None:
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
        if response.status_code == 200:
            return cast(list[dict[str, object]], response.json())
        st.sidebar.caption("History tracker offline!")
    except requests.exceptions.RequestException as connection_offline_error:
        logger.warning(
            f"Unable to read connection tracking indexes: {connection_offline_error}"
        )
        st.sidebar.caption("History tracker offline!")
    return None


def _find_active_selection_option(
    mapping: dict[str, dict[str, object]], active_id: object
) -> str:
    if not active_id:
        return "-- Create New Run --"
    for opt, task in mapping.items():
        if str(task.get("task_id")) == str(active_id):
            return opt
    return "-- Create New Run --"


def render_historical_sidebar() -> None:
    """
    Fetches the history of completed tasks and displays
    them on the sidebar dropdown so users can scroll through past runs.
    """
    past_tasks = _fetch_past_tasks_raw()
    if past_tasks is None:
        return

    completed_historical_tasks = [
        task for task in past_tasks if task.get("status") == "COMPLETED"
    ]

    if not completed_historical_tasks:
        st.sidebar.caption("No history")
        return

    # Maps display name to full task data
    task_display_options_mapping = {
        (
            f"{task.get('custom_name')} ({str(task['task_id'])[:8]})"
            if task.get("custom_name")
            else f"Job {str(task['task_id'])[:8]}"
        ): task
        for task in completed_historical_tasks
    }

    st.session_state.task_mapping = task_display_options_mapping
    available_selection_options_list = [
        "-- Create New Run --",
        *task_display_options_mapping,
    ]

    currently_active_task_id = st.session_state.get("current_task_id")
    st.session_state.history_selectbox = _find_active_selection_option(
        task_display_options_mapping, currently_active_task_id
    )

    st.sidebar.selectbox(
        "Reload a past analysis:",
        options=available_selection_options_list,
        key="history_selectbox",
        on_change=_on_history_change,
        disabled=st.session_state.get("job_running", False),
    )

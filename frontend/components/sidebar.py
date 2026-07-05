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


def _on_history_change() -> None:
    """
    Handles transition of historical task selection to keep the UI clean.
    """
    currently_selected_historical_run: str | None = st.session_state.get(
        "history_selectbox"
    )
    if not currently_selected_historical_run:
        return

    if currently_selected_historical_run == "-- Create New Run --":
        active_view_session_keys: list[str] = [
            "generator_report",
            "source_context",
            "audit_metrics",
            "current_task_id",
            "current_task_custom_name",
        ]
        for session_key_to_purge in active_view_session_keys:
            st.session_state.pop(session_key_to_purge, None)
        return

    task_id_mapping = st.session_state.get("task_mapping")
    if not isinstance(task_id_mapping, dict):
        return

    selected_job_data = task_id_mapping.get(currently_selected_historical_run)
    if not isinstance(selected_job_data, dict):
        return

    task_id: str | None = cast(str | None, selected_job_data.get("task_id"))
    if not task_id:
        return

    try:
        task_profile_response = requests.get(
            f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5
        )
    except requests.exceptions.RequestException as network_transport_fault:
        logger.error(
            "Network communication loss when trying to read historical data.",
            exc_info=True,
        )
        st.error(
            "Network error trying to fetch historical profile: "
            f"{network_transport_fault}"
        )
        return

    if task_profile_response.status_code != 200:
        st.error("Failed to extract full analysis data from backend")
        return

    job_details_payload: dict[str, object] = task_profile_response.json()

    st.session_state.current_task_id = task_id
    st.session_state.generator_report = job_details_payload.get("report")
    st.session_state.source_context = job_details_payload.get("source_context")
    st.session_state.current_task_custom_name = job_details_payload.get("custom_name")

    historical_audit_records = st.session_state.get("historical_audits")
    if not isinstance(historical_audit_records, dict):
        st.session_state.audit_metrics = None
        return

    st.session_state.audit_metrics = historical_audit_records.get(task_id)


def render_historical_sidebar() -> None:
    """
    Fetches the history of completed tasks and displays
    them on the sidebar dropdown so users can scroll through past runs.
    """
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
    except requests.exceptions.RequestException as connection_offline_error:
        logger.warning(
            f"Unable to read connection tracking indexes: {connection_offline_error}"
        )
        st.sidebar.caption("History tracker offline!")
        return

    if response.status_code != 200:
        st.sidebar.caption("History tracker offline!")
        return

    past_tasks = response.json()
    completed_historical_tasks = [
        task for task in past_tasks if task.get("status") == "COMPLETED"
    ]

    if not completed_historical_tasks:
        st.sidebar.caption("No history")
        return

    # Maps display name to full task data
    task_display_options_mapping = {
        (
            f"{task.get('custom_name')} ({task['task_id'][:8]})"
            if task.get("custom_name")
            else f"Job {task['task_id'][:8]}"
        ): task
        for task in completed_historical_tasks
    }

    st.session_state.task_mapping = task_display_options_mapping
    available_selection_options_list = [
        "-- Create New Run --",
        *task_display_options_mapping,
    ]

    currently_active_task_id = st.session_state.get("current_task_id")
    if currently_active_task_id:
        matching_selection_option_name = next(
            (
                opt
                for opt, task in task_display_options_mapping.items()
                if str(task["task_id"]) == str(currently_active_task_id)
            ),
            None,
        )
        if matching_selection_option_name:
            st.session_state.history_selectbox = matching_selection_option_name
        else:
            st.session_state.history_selectbox = "-- Create New Run --"
    else:
        st.session_state.history_selectbox = "-- Create New Run --"

    st.sidebar.selectbox(
        "Reload a past analysis:",
        options=available_selection_options_list,
        key="history_selectbox",
        on_change=_on_history_change,
        disabled=st.session_state.get("job_running", False),
    )

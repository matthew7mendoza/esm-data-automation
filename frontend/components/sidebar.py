"""
Handles historical states and user settings sidebar rendering
"""

import logging
from typing import Final, cast

import requests
import streamlit as st

from frontend.ui_constants import BACKEND_URL

__all__ = ["delete_historical_task", "purge_active_view", "render_historical_sidebar"]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def _fetch_task_profile(task_id: str) -> dict[str, object] | None:
    response = None
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
    except requests.exceptions.RequestException as network_transport_fault:
        logger.error(
            "Network communication loss when trying to read historical data.",
            exc_info=True,
        )
        st.error(
            "Network error trying to fetch historical profile: "
            f"{network_transport_fault}"
        )

    if not response:
        return None

    if response.status_code != 200:
        st.error("Failed to extract full analysis data from backend")
        return None

    return cast(dict[str, object], response.json())


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


def purge_active_view() -> None:
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
    if run_name == "Select a past run...":
        purge_active_view()
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
    if job_details_payload is None:
        return

    _update_session_state_with_task(task_id, job_details_payload)


def _on_new_click() -> None:
    purge_active_view()
    st.session_state.history_selectbox = "Select a past run..."


def _on_delete_click(task_id: str | None) -> None:
    if not task_id:
        return
    success = delete_historical_task(task_id)
    if not success:
        return
    purge_active_view()
    st.session_state.history_selectbox = "Select a past run..."


def _fetch_past_tasks_raw() -> list[dict[str, object]] | None:
    response = None
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
    except requests.exceptions.RequestException as connection_offline_error:
        logger.warning(
            f"Unable to read connection tracking indexes: {connection_offline_error}"
        )
        st.sidebar.caption("History tracker offline!")

    if not response:
        return None

    if response.status_code != 200:
        st.sidebar.caption("History tracker offline!")
        return None

    return cast(list[dict[str, object]], response.json())


def _find_active_selection_option(
    mapping: dict[str, dict[str, object]], active_id: object
) -> str:
    if not active_id:
        return "Select a past run..."

    matching_opts = [
        opt
        for opt, task in mapping.items()
        if str(task.get("task_id")) == str(active_id)
    ]
    if not matching_opts:
        return "Select a past run..."

    return matching_opts[0]


def _send_delete_call(task_id: str) -> requests.Response | None:
    try:
        return requests.delete(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
    except requests.exceptions.RequestException as err:
        logger.error(f"Error deleting task {task_id}: {err}", exc_info=True)
        st.error(f"Network error trying to delete run: {err}")
        return None


def _remove_audit_from_session(task_id: str) -> None:
    historical_audits = st.session_state.get("historical_audits")
    if isinstance(historical_audits, dict):
        historical_audits.pop(task_id, None)


def delete_historical_task(task_id: str) -> bool:
    response = _send_delete_call(task_id)
    if not response:
        return False

    if response.status_code != 200:
        st.error("Failed to delete task from backend database")
        return False

    _remove_audit_from_session(task_id)
    st.toast("Run deleted successfully!")
    return True


def render_historical_sidebar() -> None:
    """
    Fetches the history of completed tasks and displays
    them on the sidebar dropdown so users can scroll through past runs.
    """
    st.sidebar.markdown(
        "<div style='font-size: 0.75rem; font-weight: 700; "
        "letter-spacing: 0.05em; color: #6b7280; text-transform: uppercase; "
        "margin-top: 2rem; margin-bottom: 0.5rem; padding-left: 12px;'>"
        "Session Management</div>",
        unsafe_allow_html=True,
    )

    past_tasks = _fetch_past_tasks_raw()
    completed_historical_tasks = []
    if past_tasks is not None:
        completed_historical_tasks = [
            task for task in past_tasks if task.get("status") == "COMPLETED"
        ]

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
        "Select a past run...",
        *task_display_options_mapping,
    ]

    currently_active_task_id = st.session_state.get("current_task_id")
    st.session_state.history_selectbox = _find_active_selection_option(
        task_display_options_mapping, currently_active_task_id
    )

    is_job_running = bool(st.session_state.get("job_running"))

    st.sidebar.selectbox(
        "Reload a past analysis:",
        options=available_selection_options_list,
        key="history_selectbox",
        on_change=_on_history_change,
        disabled=is_job_running,
    )

    col1, col2 = st.sidebar.columns(2)

    col1.button(
        "+ New",
        key="new_run_sidebar_btn",
        type="secondary",
        use_container_width=True,
        disabled=is_job_running,
        on_click=_on_new_click,
    )

    col2.button(
        "Delete Current",
        key="delete_run_sidebar_btn",
        type="secondary",
        use_container_width=True,
        disabled=not currently_active_task_id or is_job_running,
        on_click=_on_delete_click,
        args=(currently_active_task_id,),
    )

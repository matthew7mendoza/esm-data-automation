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
    prevents ui from getting messy
    by keeping track of what process is going on 
    """

    selected_job_name: str | None = st.session_state.get("history_selectbox")
    if not selected_job_name:
        return
    if selected_job_name == "-- Select Past Run --":
        return
    
    chosen_job: dict[str, object] = (
        st.session_state.get("task_mapping", {})
        .get(selected_job_name, {})
    )
    task_id: str | None = cast(str | None, chosen_job.get("task_id"))
    if not task_id: 
        return
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
    except requests.exceptions.RequestException as network_transport_fault:
        logger.error(
            "Network communication loss when trying to read historical data.",
            exc_info=True
        )
        st.error(
            f"Netowkr error trying to fetch historical profile: {network_transport_fault}"
        )
        return
    
    if response.status_code != 200:
        st.error("Failed to extract full analysis data from backend")
        return
    
    full_job_payload: dict[str, object] = response.json()

    st.session_state.current_task_id = task_id
    st.session_state.generator_report = full_job_payload.get("report")
    st.session_state.source_context = full_job_payload.get("source_context")

    historical_audits: dict[str, dict[str, object]] = st.session_state.get(
        "historical_audits", {}
    )
    st.session_state.audit_metrics = historical_audits.get(task_id)

def render_historical_sidebar() -> None:
    """
    fetches the history of completed tasks and displays
    them on the sidebar dropdown so users can scroll through past runs
    """

    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
    except requests.exceptions.RequestException as connection_offline_error:
        logger.warning(f"Unable to read connection tracking indexes: {connection_offline_error}")
        st.sidebar.caption("History tracker offline!")
        return
    
    if response.status_code != 200:
        st.sidebar.caption("History tracker offline!")
        return
    
    past_tasks = response.json()
    completed_tasks = [
        task for task in past_tasks if task.get("status") == "COMPLETED"
    ]

    if not completed_tasks:
        st.sidebar.caption("No history")
        return
    
    # maps display name to full task data
    # uses the custom name if avaliable, otherwise defaults to 
    # job [first 8 characters of ID]
    task_options = {
        (
            f"{task.get('custom_name')} ({task['task_id'][:8]})"
            if task.get("custom_name")
            else f"Job {task['task_id'][:8]}"
        ): task
        for task in completed_tasks
    }

    st.session_state.task_mapping = task_options
    options_list = ["-- Select Past Run --", *task_options]

    st.sidebar.selectbox(
        "Reload a past analysis:",
        options=options_list,
        key="history_selectbox",
        on_change=_on_history_change,
        disabled=st.session_state.get("job_running", False),
    )

    

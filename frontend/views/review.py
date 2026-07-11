"""
Review and edit completed AI tasks.
"""

import difflib
import logging
import time
from typing import Final

import streamlit as st

from frontend.client import (
    approve_pending_update,
    fetch_pending_context,
    get_task_profile,
    update_task_report,
)
from frontend.protocols import TaskProfileDict
from shared.models import TaskId

__all__ = ["render_review_view"]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def _poll_task_status(task_id: str) -> TaskProfileDict | None:
    """Fetches task status, triggering a rerun if still processing."""
    task_status = get_task_profile(task_identifier=TaskId(task_id))
    if not task_status:
        st.error(
            "Tracking code not found in the database. "
            "Are you sure you have the right link?"
        )
        return None

    status_str = str(task_status.get("status", ""))

    if status_str == "PENDING_REVIEW":
        return task_status

    if status_str in ("PENDING", "PROCESSING"):
        with st.status(f"Task is {status_str}...", expanded=True):
            st.write(
                "The AI is currently processing the data "
                "and reviewing formatting conventions..."
            )
            st.write("Please wait. This page will automatically update.")

        time.sleep(2)
        st.rerun()

    if status_str == "FAILED":
        st.error(
            f"Task failed to generate: {task_status.get('detail', 'Unknown error')}"
        )
        return None

    return task_status


def render_review_view(*, disabled: bool) -> None:  # noqa: C901
    """Renders the hidden human-in-the-loop review page."""

    task_id = st.session_state.get("current_task_id")
    if not task_id:
        st.error("No Task ID provided.")
        return

    st.markdown(
        "<div style='text-align: center; margin-bottom: 2rem;'>"
        f"<h2>Review Dashboard: {task_id[:8]}</h2>"
        "</div>",
        unsafe_allow_html=True,
    )

    task_data = _poll_task_status(task_id)
    if not task_data:
        return

    status_str = str(task_data.get("status", ""))
    if status_str == "PENDING_REVIEW":
        _render_pending_review_ui(task_id)
        return

    report = task_data.get("report")
    if not isinstance(report, dict):
        st.error("Invalid report format received from server.")
        return

    extracted_answers = report.get("extracted_answers", {})
    if not isinstance(extracted_answers, dict):
        st.error("Invalid extracted answers format.")
        return

    st.success("Your automated documentation is ready for review!")
    st.markdown(
        "Please verify the AI's extractions below. You can manually edit any field."
    )

    # Render interactive text areas for human-in-the-loop
    edited_answers = {}
    with st.form(key="review_form"):
        for question, answer in extracted_answers.items():
            edited_answers[question] = st.text_area(
                label=question,
                value=str(answer),
                height=150,
                disabled=disabled,
            )

        col1, col2 = st.columns([1, 1])
        with col1:
            save_clicked = st.form_submit_button(
                "Approve & Save Changes", type="primary", use_container_width=True
            )
        with col2:
            st.markdown(
                "<p style='text-align: center; font-size: 0.9em; color: gray; "
                "margin-top: 10px;'>"
                "All edits will be permanently saved to the master database."
                "</p>",
                unsafe_allow_html=True,
            )

    if save_clicked:
        success = update_task_report(
            task_identifier=task_id,
            extracted_answers=edited_answers,
            missing_information=report.get("missing_information", []),
        )
        if success:
            st.success("Corrections saved successfully!")
            # Update local session memory
            report["extracted_answers"] = edited_answers
            task_data["report"] = report
        else:
            st.error("Failed to save corrections to the database.")

    st.divider()

    # Export Options
    st.markdown("### Export Final Document")
    st.markdown("Download your finalized document to your local machine.")

    export_content = "\\n\\n".join(
        [f"### {q}\\n{a}" for q, a in extracted_answers.items()]
    )

    dl_col1, dl_col2, dl_col3 = st.columns(3)
    with dl_col1:
        st.download_button(
            label="Download as README.md",
            data=export_content,
            file_name=f"README_{task_id[:8]}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl_col2:
        st.download_button(
            label="Download as DMP.txt",
            data=export_content,
            file_name=f"DMP_{task_id[:8]}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with dl_col3:
        if st.button("Create Custom Form Template", use_container_width=True):
            st.query_params.clear()
            st.session_state.selected_template = "SETTINGS"
            st.rerun()


def _render_pending_review_ui(task_id: str) -> None:
    """Renders the side-by-side visual difference when an update is pending approval."""
    st.info(
        "A new metadata update has been submitted and is waiting for your approval.",
    )

    contexts = fetch_pending_context(task_id)
    if not contexts:
        st.error("Failed to load the file differences from the server.")
        return

    original_text = str(contexts.get("original", ""))
    pending_text = str(contexts.get("pending", ""))

    st.markdown("### Review File Differences")
    st.markdown(
        "Please review the changes submitted from the scanner before proceeding."
    )

    original_lines = original_text.splitlines()
    pending_lines = pending_text.splitlines()

    difference_html = difflib.HtmlDiff().make_table(
        original_lines,
        pending_lines,
        "Current Database State",
        "Incoming Update",
        context=True,
        numlines=3,
    )

    st.components.v1.html(difference_html, height=500, scrolling=True)

    if st.button("Approve Overwrite & Run Update", type="primary"):
        success = approve_pending_update(task_id)
        if success:
            st.success(
                "Update approved! The system is now generating the new document."
            )
            time.sleep(1.5)
            st.rerun()
        else:
            st.error("Failed to approve the update. Please check network connection.")

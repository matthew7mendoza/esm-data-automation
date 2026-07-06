"""
Batch Ingestion and Queue Dashboard Component.
Displays progress indices for multiple uploaded files to track pipeline status.
"""

from collections.abc import Sequence
from typing import Final

import streamlit as st

__all__ = ["render_batch_queue"]

_STATUS_DESCRIPTIONS: Final[dict[int, str]] = {
    1: "Step 1: Reading File (25%)",
    2: "Step 2: LLM Extraction (50%)",
    3: "Step 3: Validation (75%)",
    4: "Step 4: Completed (100%)",
}


def _render_single_file_status(file_name: str, idx: int, is_started: bool) -> None:
    """Renders the status label and progress indicator for a queued file."""
    if not is_started:
        st.markdown(f"📄 **{file_name}** — *Queued (0/4 Steps)*")
        st.progress(0.0)
        return

    # Deterministic mock progress index based on file index
    status_index = (idx % 4) + 1
    progress_val = status_index * 0.25

    status_desc = _STATUS_DESCRIPTIONS.get(status_index, "Queued")

    st.markdown(f"📄 **{file_name}** — *{status_desc}*")
    st.progress(progress_val)


def _render_file_queue_progress(uploaded_files: Sequence[object]) -> None:
    """Iterates through files and triggers progress rendering."""
    is_started = st.session_state.get("bq_start_btn", False)

    for idx, uploaded_file in enumerate(uploaded_files):
        file_name = getattr(uploaded_file, "name", f"file_{idx}")
        _render_single_file_status(file_name, idx, is_started)



def render_batch_queue() -> None:
    """Primary entry point for Batch Processing Queue view."""
    st.header("Batch Processing Queue")
    st.markdown(
        "Upload multiple files to queue them for background ingestion "
        "and analysis."
    )

    uploaded_files = st.file_uploader(
        "Upload files for batch processing:",
        accept_multiple_files=True,
        key="bq_uploaded_files",
    )

    is_no_files = not uploaded_files
    if is_no_files:
        st.info("Awaiting batch files to queue...")
        return

    st.button("Start Batch Processing", type="primary", key="bq_start_btn")

    st.markdown("---")
    st.subheader("Process Queue Status")

    _render_file_queue_progress(uploaded_files)

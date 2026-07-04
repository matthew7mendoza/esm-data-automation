"""
Renders targeted metrics and data extraction visualizations cleanly
"""

import re
from typing import Final
import streamlit as st

from frontend.api import update_task_report

__all__ = ["render_answers_and_missing_sections", "render_trust_audit_ledger"]

def extract_source_assets(*, source_context: str | None) -> list[str]:
    """
    Parses raw text payloads to extract source filenames
    """

    if not source_context:
        return []
    
    # regex finds filenames between markers ---SOURCE CONTENT ASSET: and ---
    marker_pattern: Final[str] = r"--- SOURCE CONTENT ASSET:\s*(.*?)\s---"
    return re.findall(marker_pattern, source_context)

def render_trust_audit_ledger(*, source_context: str | None) -> None:
    """
    Renders a structured data history that shows which historical document the LLM judge is evaluating
    """

    if not source_context:
        return
    
    contributing_files: list[str] = extract_source_assets(source_context=source_context)
    if not contributing_files:
        st.warning("No explicit source context assets detected!")
        return
    
    with st.expander("History Audit Files", expanded=True):
        st.markdown("**Files being verified:**")
        for file_name in contributing_files:
            st.markdown(f"- '{file_name}'")

def render_answers_and_missing_sections(*, disabled: bool = False) -> None:
    """
    Renders a unified form allowing users to view, edit, and fill in all questions.
    Saves edited answers back to the database and session state.
    """

    current_task_id = st.session_state.get("current_task_id")
    report = st.session_state.get("generator_report")
    if not current_task_id or not isinstance(report, dict):
        return

    st.header("2. Review & Edit Answers")
    st.markdown(
        "Below are the answers extracted by the AI and any missed questions. "
        "You can edit any field, and the changes will be saved to the database and final document."
    )

    extracted_answers: dict[str, str] = report.get("extracted_answers") or {}
    missing_information: list[str] = report.get("missing_information") or []

    # We use st.form to capture all edits atomically
    with st.form(key=f"edit_form_{current_task_id}"):
        tab_extracted, tab_missing = st.tabs(
            ["Extracted Answers", "Missing / Additional Information"]
        )

        updated_extracted: dict[str, str] = {}
        updated_missing: list[str] = []

        with tab_extracted:
            if not extracted_answers:
                st.info("No answers were extracted by the AI.")
            else:
                for question, answer in extracted_answers.items():
                    field_key = f"ans_{current_task_id}_{question}"
                    user_val = st.text_area(
                        label=question,
                        value=answer,
                        key=field_key,
                        disabled=disabled
                    )
                    if user_val.strip():
                        updated_extracted[question] = user_val.strip()
                    else:
                        updated_missing.append(question)

        with tab_missing:
            if not missing_information:
                st.success("All questions have answers! No missing fields.")
            else:
                st.info("The AI missed these questions. You can fill them in below:")
                for question in missing_information:
                    field_key = f"ans_{current_task_id}_{question}"
                    user_val = st.text_area(
                        label=question,
                        value="",
                        key=field_key,
                        disabled=disabled
                    )
                    if user_val.strip():
                        updated_extracted[question] = user_val.strip()
                    else:
                        updated_missing.append(question)

        col1, _ = st.columns([1, 4])
        with col1:
            save_button = st.form_submit_button("Save Changes", disabled=disabled)

        if save_button:
            success = update_task_report(
                task_id=current_task_id,
                extracted_answers=updated_extracted,
                missing_information=updated_missing
            )
            if success:
                new_report = {
                    "extracted_answers": updated_extracted,
                    "missing_information": updated_missing
                }
                st.session_state.generator_report = new_report
                st.toast("Changes saved successfully!")
                st.rerun()
            else:
                st.error("Failed to save changes to backend database.")
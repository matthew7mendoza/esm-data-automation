"""
Renders targeted metrics and data extraction visualizations cleanly
"""

import re
from typing import Final
import streamlit as st

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

def render_answers_and_missing_sections() -> None:
    """
    Displays the successfully extracted answers and any 
    missing information side-by-side using two columns
    """

    generator_report = st.session_state.get("generator_report")
    if not isinstance(generator_report, dict):
        return
    
    st.markdown("---")
    left_column, right_column = st.columns(2)

    with left_column:
        st.subheader("Extracted Answers")
        answers = generator_report.get("extracted_answers")
        if isinstance(answers, dict):
            for question, answer in answers.items():
                st.markdown(f"**{question}**\n> {answer}")
    
    with right_column:
        st.subheader("Missing Information")
        missing = generator_report.get("missing_information")
        if not isinstance(missing, list):
            return

        if not missing:
            st.success("The AI found answers to all questions for this template!!!")
            return
        
        for missing_question in missing:
            st.error(f"- {missing_question}")
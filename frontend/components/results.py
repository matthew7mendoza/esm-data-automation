"""
Renders targeted metrics and data extraction visualizations cleanly
"""

import re
import streamlit as st

__all__ = ["render_answers_and_missing_sections", "render_trust_audit_ledger"]

def extract_source_assets(*, source_context: str | None) -> list[str]:
    """
    Parses raw text payloads to extract source filenames
    """

    if not source_context:
        return []
    
    # regex finds filenames between markers ---SOURCE CONTENT ASSET: and ---
    marker_pattern: str = r"--- SOURCE CONTENT ASSET:\s*(.*?)\s---"
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
    
    with st.expander("History Audit Files", expander=True):
        st.markdown("**Files being verified:**")
        for file_name in contributing_files:
            st.markdown(f"- '{file_name}'")

def render_answers_and_missing_sections() -> None:
    """
    Displays the successfully extracted answers and any 
    missing information side-by-side using two columns
    """

    if not st.session_state.generator_report:
        return
    
    st.markdown("---")
    left_column, right_column = st.columns(2)

    with left_column:
        st.subheader("Extracted Answers")
        answers = st.session_state.generator_report.get("extracted_answers", {})
        for question, answer in answers.items():
            st.markdown(f"**{question}**\n> {answer}")
    
    with right_column:
        st.subheader("Missing Information")
        missing = st.session_state.generator_report.get("missing_information", [])

        if not missing:
            st.success("The AI found answers to all questions for this template!!!")
            return
        
        for missing_question in missing:
            st.error(f"- {missing_question}")
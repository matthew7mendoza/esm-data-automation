"""
Document generator workspace tab view.
"""

from typing import cast

import streamlit as st

from frontend.components.results import render_answers_and_missing_sections
from frontend.ui_constants import TEMPLATE_DESCRIPTIONS, TEMPLATE_DISPLAY_NAMES
from frontend.utils.document import build_final_document_string, create_docx_buffer

__all__ = ["render_generator_tab_view"]


def _render_step_one_upload(*, disabled: bool, target_document: str) -> None:
    """
    Renders step 1: File upload layout.
    """
    display_name = TEMPLATE_DISPLAY_NAMES.get(target_document, target_document)
    st.header(f"1. Generate {display_name}")

    form_description = TEMPLATE_DESCRIPTIONS.get(target_document)
    if form_description:
        st.markdown(form_description)

    uploaded_files = st.file_uploader(
        "Drop your scientific data, READMEs, publications, ect... here:",
        accept_multiple_files=True,
        disabled=disabled,
    )

    custom_name = st.text_input(
        "Label this extraction run (optional):",
        placeholder="Project #1",
        disabled=disabled,
    )

    if uploaded_files:
        trigger_generation = st.button(
            "Read Files & Write Answers",
            type="primary",
            use_container_width=True,
            disabled=disabled,
        )
    else:
        trigger_generation = st.button(
            "Read Files & Write Answers",
            type="secondary",
            use_container_width=True,
            disabled=True,
        )

    if not trigger_generation:
        return

    st.session_state.job_running = True
    st.session_state.run_state = "triggered"
    st.session_state.pending_generation = {
        "target_document": target_document,
        "chosen_engine": st.session_state.get("global_chosen_engine", "Gemini"),
        "uploaded_files": uploaded_files,
        "custom_name": custom_name,
    }
    st.rerun()


def _render_step_three_download(
    *,
    target_document: str,
    extracted: dict[str, str],
    missing: list[str],
    disabled: bool,
) -> None:
    """
    Renders step 3: Export/Download options.
    """
    st.header("3. Download Final Document")

    download_format = st.radio(
        "Choose Download Format",
        options=["Markdown (.md)", "Microsoft Word (.docx)"],
        horizontal=True,
        disabled=disabled,
    )

    base_name = f"{target_document}_completed"
    custom_name = st.session_state.get("current_task_custom_name")
    if isinstance(custom_name, str) and custom_name.strip():
        cleaned_name = custom_name.strip()
        for char in r'\/:*?"<>|':
            cleaned_name = cleaned_name.replace(char, "_")
        base_name = cleaned_name

    if download_format == "Markdown (.md)":
        final_markdown: str = build_final_document_string(
            extracted_answers=extracted, missing_questions=missing
        )
        st.download_button(
            label="Download Document (.md)",
            data=final_markdown,
            file_name=f"{base_name}.md",
            mime="text/markdown",
            type="primary",
            disabled=disabled,
        )
        return

    final_docx: bytes = create_docx_buffer(
        extracted_answers=extracted, missing_questions=missing
    )
    st.download_button(
        label="Download Document (.docx)",
        data=final_docx,
        file_name=f"{base_name}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        disabled=disabled,
    )


def render_generator_tab_view(*, disabled: bool, target_document: str) -> None:
    """
    Renders the document generation tab content.
    """
    _render_step_one_upload(disabled=disabled, target_document=target_document)

    report = cast(dict[str, object] | None, st.session_state.get("generator_report"))
    if not report:
        return

    render_answers_and_missing_sections(disabled=disabled)
    st.markdown("---")

    missing_question: list[str] = cast(list[str], report.get("missing_information", []))
    extracted_answers: dict[str, str] = cast(
        dict[str, str], report.get("extracted_answers", {})
    )

    _render_step_three_download(
        target_document=target_document,
        extracted=extracted_answers,
        missing=missing_question,
        disabled=disabled,
    )

    audit_metrics = cast(
        dict[str, object] | None, st.session_state.get("audit_metrics")
    )
    if not audit_metrics:
        return

    st.markdown("---")
    st.subheader("Complete run snapshot")
    metadata = cast(dict[str, object], audit_metrics.get("metadata", {}))
    kappa_score = cast(
        float,
        metadata.get("global_gwet_ac1") or metadata.get("global_gwets_ac1", 0.0),
    )

    st.metric("Agreement score (Gwet's AC1)", f"{kappa_score:.3f}")
    st.dataframe(
        cast(list[object], audit_metrics.get("item_level_stability_metrics", [])),
        use_container_width=True,
    )

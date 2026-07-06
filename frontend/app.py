"""
Primary streamlit rendering
"""

import io
import logging
from typing import Final, cast

import streamlit as st
from docx import Document

from frontend.api import fetch_all_historical_tasks, fetch_server_templates
from frontend.components.results import (
    render_answers_and_missing_sections,
    render_trust_audit_ledger,
)
from frontend.components.sidebar import render_historical_sidebar
from frontend.config import MODEL_CONFIGURATIONS, TEMPLATE_DISPLAY_NAMES, TEMPLATE_DESCRIPTIONS
from frontend.protocols import UploadedFileProtocol
from frontend.services import send_audit_request, send_generation_request

__all__ = ["main"]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def _initialize_session_state() -> None:
    """
    Set up core streamlit session with explicit mutation
    """

    defaults: dict[str, bool | dict[str, object] | str | None] = {
        "generator_report": None,
        "source_context": None,
        "audit_metrics": None,
        "job_running": False,
        "current_task_id": None,
        "current_task_custom_name": None,
        "historical_audits": {},
        "run_state": "idle",
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _handle_pending_generation(generation_args: object) -> None:
    if not isinstance(generation_args, dict):
        return
    send_generation_request(
        target_document=cast(str, generation_args.get("target_document", "")),
        chosen_engine=cast(str, generation_args.get("chosen_engine", "")),
        uploaded_files=cast(
            list[UploadedFileProtocol],
            generation_args.get("uploaded_files", []),
        ),
        custom_name=cast(str, generation_args.get("custom_name", "")),
    )
    st.session_state.job_running = False
    st.rerun()


def _handle_pending_audit(audit_args: object) -> None:
    if not isinstance(audit_args, dict):
        return
    args_copy = dict(audit_args)
    task_id: str = str(args_copy.pop("task_id", ""))
    metrics = send_audit_request(
        chosen_engine=cast(str, args_copy.get("chosen_engine", "")),
        answers=cast(dict[str, str], args_copy.get("answers", {})),
        judge_iterations=cast(int, args_copy.get("judge_iterations", 3)),
        source_context=cast(str, args_copy.get("source_context", "")),
    )
    if metrics:
        st.session_state.audit_metrics = metrics
        historical_audits = st.session_state.get("historical_audits")
        if not isinstance(historical_audits, dict):
            historical_audits = {}
        historical_audits[task_id] = metrics
        st.session_state.historical_audits = historical_audits

    st.session_state.job_running = False
    st.rerun()


def _should_execute_pending_job() -> bool:
    if not st.session_state.get("job_running"):
        return False
    run_state = st.session_state.get("run_state", "idle")
    if run_state == "triggered":
        st.session_state.run_state = "executing"
        return False
    if run_state != "executing":
        return False
    st.session_state.run_state = "idle"
    return True


def _process_pending_jobs() -> None:
    """
    Executes queded background tasks
    then refreshes the app
    """

    if not _should_execute_pending_job():
        return

    if "pending_generation" in st.session_state:
        _handle_pending_generation(st.session_state.pop("pending_generation"))
        return

    if "pending_audit" in st.session_state:
        _handle_pending_audit(st.session_state.pop("pending_audit"))
        return


def _purge_workspace_heap() -> None:
    """
    Removes active tracking keys to reset the UI
    to baseline so things don't get messy
    """

    transient_keys: list[str] = [
        "generator_report",
        "source_context",
        "audit_metrics",
        "current_task_id",
        "current_task_custom_name",
    ]
    for key in transient_keys:
        st.session_state.pop(key, None)


def _render_workspace_cleaner() -> None:
    """
    Renders workspace reset controls to start a fresh extraction run.
    """
    has_active_analysis_view: bool = bool(
        st.session_state.get("generator_report")
        or st.session_state.get("audit_metrics")
    )
    if not has_active_analysis_view:
        return

    if st.button("Create New Run", type="secondary"):
        _purge_workspace_heap()
        st.session_state.history_selectbox = "-- Create New Run --"
        st.rerun()


def _render_sidebar_navigation(*, disabled: bool, templates: list[str]) -> str:
    """
    Renders the sidebar page navigation: the overview landing page
    followed by one page per form template.
    Returns the active page (OVERVIEW_PAGE or a template key)
    """

    selected_page: str = st.session_state.get("selected_template", OVERVIEW_PAGE)
    if selected_page != OVERVIEW_PAGE and selected_page not in templates:
        selected_page = OVERVIEW_PAGE
        st.session_state.selected_template = selected_page

    if st.sidebar.button(
        "Overview",
        key="page_overview",
        type="primary" if selected_page == OVERVIEW_PAGE else "secondary",
        width="stretch",
        disabled=disabled,
    ):
        st.session_state.selected_template = OVERVIEW_PAGE
        st.rerun()

    st.sidebar.subheader("Form templates")

    for template_name in templates:
        if st.sidebar.button(
            TEMPLATE_DISPLAY_NAMES.get(template_name, template_name),
            key=f"template_page_{template_name}",
            type="primary" if template_name == selected_page else "secondary",
            width="stretch",
            disabled=disabled,
        ):
            st.session_state.selected_template = template_name
            st.rerun()

    return selected_page

def _render_overview_page() -> None:
    """
    Placeholder landing page, real content to be filled in later
    """

    st.header("Overview Title Placeholder")
    st.write("Overview text placeholder.")

def _render_step_one_upload(
    *, disabled: bool, templates: list[str], models: list[str]
) -> str:
    """
    Renders the sidebar settings and step 1 upload form
    """

    st.sidebar.header("Settings")

    chosen_engine: str = st.sidebar.selectbox(
        "Select AI Model",
        models,
        disabled=disabled,
    )

    display_name: str = TEMPLATE_DISPLAY_NAMES.get(target_document, target_document)

    st.header(f"1. Generate {display_name}")

    form_description: str | None = TEMPLATE_DESCRIPTIONS.get(target_document)
    if form_description:
        st.markdown(form_description)

    uploaded_files = st.file_uploader(
        "Drop your scientific data, READMEs, publications, ect... here:",
        accept_multiple_files=True,
        disabled=disabled,
    )

    custom_name: str = st.text_input(
        "Label this extraction run (optional):",
        placeholder="Project #1",
        disabled=disabled,
    )

    if st.button(
        "Read Files & Write Answers",
        type="primary",
        disabled=not uploaded_files or disabled,
    ):
        st.session_state.job_running = True
        st.session_state.run_state = "triggered"
        st.session_state.pending_generation = {
            "target_document": target_document,
            "chosen_engine": chosen_engine,
            "uploaded_files": uploaded_files,
            "custom_name": custom_name,
        }
        st.rerun()
    return target_document


def _build_final_document_string(
    *, extracted_answers: dict[str, str], missing_questions: list[str]
) -> str:
    """
    Aggregates text chunks
    """

    document_blocks: list[str] = ["# Final Extracted Document\n\n"]

    for question_text, answer_text in extracted_answers.items():
        document_blocks.append(f"### {question_text}\n{answer_text}\n\n")

    for question_text in missing_questions:
        if question_text not in extracted_answers:
            document_blocks.append(f"### {question_text}\n*No answer provided*\n\n")

    return "".join(document_blocks)


def _create_docx_buffer(
    *, extracted_answers: dict[str, str], missing_questions: list[str]
) -> bytes:
    """
    Generates a Microsoft Word (.docx) document in memory and returns bytes.
    """

    doc = Document()
    doc.add_heading("Final Extracted Document", level=0)

    for question_text, answer_text in extracted_answers.items():
        doc.add_heading(question_text, level=2)
        doc.add_paragraph(answer_text)

    for question_text in missing_questions:
        if question_text not in extracted_answers:
            doc.add_heading(question_text, level=2)
            p = doc.add_paragraph()
            p.add_run("No answer provided").italic = True

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _render_step_three_download(
    *,
    target_document: str,
    extracted: dict[str, str],
    missing: list[str],
    disabled: bool,
) -> None:
    """
    Provides the final aggregated document for download
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
    if custom_name and isinstance(custom_name, str) and custom_name.strip():
        cleaned_name = custom_name.strip()
        for char in r'\/:*?"<>|':
            cleaned_name = cleaned_name.replace(char, "_")
        base_name = cleaned_name

    if download_format == "Markdown (.md)":
        final_markdown: str = _build_final_document_string(
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
    else:
        final_docx: bytes = _create_docx_buffer(
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


def _render_generator_tab(
    *, is_running: bool, templates: list[str], models: list[str]
) -> None:
    """
    Renders document filling process,
    the three step process
    """

    _render_step_one_upload(
        disabled=is_running,
        target_document=target_document,
        models=models,
    )

    report = cast(dict[str, object] | None, st.session_state.get("generator_report"))
    if not report:
        return

    render_answers_and_missing_sections(disabled=is_running)
    st.markdown("---")

    missing_question: list[str] = cast(
        list[str], report.get("missing_information", [])
    )
    extracted_answers: dict[str, str] = cast(
        dict[str, str], report.get("extracted_answers", {})
    )

    _render_step_three_download(
        target_document=target_document,
        extracted=extracted_answers,
        missing=missing_question,
        disabled=is_running,
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


def _get_currently_active_task(
    historical_tasks: list[dict[str, object]], task_id: str | None
) -> dict[str, object] | None:
    if not task_id:
        return None
    for task in historical_tasks:
        if (
            task.get("status") == "COMPLETED"
            and task.get("report") is not None
            and str(task.get("task_id")) == str(task_id)
        ):
            return task
    return None


def _trigger_stability_test(
    task_id: str,
    active_task_data: dict[str, object],
    chosen_engine: str,
    judge_iterations: int,
) -> None:
    report_data = active_task_data.get("report") or {}
    extracted_answers_dict = (
        report_data.get("extracted_answers", {})
        if isinstance(report_data, dict)
        else {}
    )

    st.session_state.job_running = True
    st.session_state.run_state = "triggered"
    st.session_state.pending_audit = {
        "task_id": task_id,
        "chosen_engine": chosen_engine,
        "judge_iterations": judge_iterations,
        "answers": extracted_answers_dict,
        "source_context": active_task_data.get("source_context", ""),
    }
    st.rerun()


def _render_audit_results(audit_metrics: dict[str, object] | None) -> None:
    if not audit_metrics:
        return
    st.markdown("---")
    st.success("Audit complete!")

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


def _render_judge_tab(*, disabled: bool, models: list[str]) -> None:
    """
    Renders the LLM Judge tab using the globally selected active run.
    """

    st.header("LLM Judge: Evaluate Historical Extraction")
    st.markdown(
        "Quantify the extraction accuracy of a past run against its "
        "original source context."
    )

    historical_tasks: list[dict[str, object]] = fetch_all_historical_tasks()
    currently_selected_task_id: str | None = st.session_state.get("current_task_id")
    currently_active_task_data = _get_currently_active_task(
        historical_tasks, currently_selected_task_id
    )

    if not currently_active_task_data:
        st.info(
            "Please upload files under the 'Document Generator' tab or "
            "select a past run from the sidebar to evaluate."
        )
        return

    # Inform the user which run is currently active and under evaluation
    active_run_custom_name = (
        currently_active_task_data.get("custom_name") or "Unnamed Run"
    )
    st.success(
        "Evaluating Active Run: "
        f"**{active_run_custom_name}** (ID: `{str(currently_selected_task_id)[:8]}`)"
    )

    chosen_engine: str = st.selectbox(
        "Select Evaluating AI Judge", models, disabled=disabled
    )

    judge_iterations: int = st.slider(
        "Testing Iterations (Higher = more accurate but much slower!)",
        min_value=2,
        max_value=10,
        value=3,
        disabled=disabled,
    )

    st.markdown("#### Original Source Documents Under Review")
    render_trust_audit_ledger(
        source_context=cast(
            str | None, currently_active_task_data.get("source_context")
        )
    )

    if st.button("Run Stability Test", type="primary", disabled=disabled):
        _trigger_stability_test(
            cast(str, currently_selected_task_id),
            currently_active_task_data,
            chosen_engine,
            judge_iterations,
        )

    audit_metrics = cast(
        dict[str, object] | None, st.session_state.get("audit_metrics")
    )
    _render_audit_results(audit_metrics)


def main() -> None:
    """
    Main control flow
    """

    st.set_page_config(page_title="ESM Data Automation", layout="wide")
    st.title("ESM Data Automation Pipeline")

    _initialize_session_state()
    _process_pending_jobs()
    _render_workspace_cleaner()

    is_running: bool = bool(st.session_state.get("job_running"))

    if is_running:
        st.warning("Active AI job currently running...")

    render_historical_sidebar()

    available_templates: list[str] = fetch_server_templates()
    available_models: list[str] = list(MODEL_CONFIGURATIONS.keys())

    tab_generator, tab_judge = st.tabs(["Document Generator", "LLM Judge Evaluation"])

    with tab_generator:
        _render_generator_tab(
            is_running=is_running,
            target_document=selected_page,
            models=available_models,
        )

    with tab_judge:
        _render_judge_tab(
            disabled=is_running,
            models=available_models,
        )

    if st.session_state.get("run_state") == "executing":
        st.rerun()


if __name__ == "__main__":
    main()

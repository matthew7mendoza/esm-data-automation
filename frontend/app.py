"""
Primary streamlit rendering
"""

import io
import logging
from typing import Final, cast

from docx import Document
import streamlit as st

from frontend.api import fetch_server_templates, fetch_all_historical_tasks
from frontend.components.results import (
    render_answers_and_missing_sections,
    render_trust_audit_ledger
)
from frontend.components.sidebar import render_historical_sidebar
from frontend.config import MODEL_CONFIGURATIONS
from frontend.protocols import UploadedFileProtocol
from frontend.services import send_audit_request, send_generation_request

__all__ = ["main"]

logger: Final[logging.Logger] = logging.getLogger(__name__)

def _initialize_session_state() -> None:
    """
    Set up core streamlit session with explicit mutation
    """

    defaults: dict[str, bool | dict | str | None] = {
        "generator_report": None,
        "source_context": None,
        "audit_metrics": None,
        "job_running": False,
        "current_task_id": None,
        "current_task_custom_name": None,
        "historical_audits": {},
        "run_state": "idle"
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

def _process_pending_jobs() -> None:
    """
    Executes queded background tasks 
    then refreshes the app
    """

    if not st.session_state.get("job_running"):
        return
    
    run_state = st.session_state.get("run_state", "idle")
    if run_state == "triggered":
        # Transition from triggered to executing. Do not execute the blocking request yet.
        # This allows Streamlit to finish rendering the current page, which will disable all buttons in the browser.
        st.session_state.run_state = "executing"
        return

    if run_state == "executing":
        # Transition from executing to idle, and now execute the actual blocking job.
        # The browser is already showing the disabled UI, so the user cannot double-click.
        st.session_state.run_state = "idle"

        if "pending_generation" in st.session_state:
            generation_args = st.session_state.pop("pending_generation")
            if isinstance(generation_args, dict):
                send_generation_request(
                    target_document=cast(str, generation_args.get("target_document", "")),
                    chosen_engine=cast(str, generation_args.get("chosen_engine", "")),
                    uploaded_files=cast(list[UploadedFileProtocol], generation_args.get("uploaded_files", [])),
                    custom_name=cast(str, generation_args.get("custom_name", ""))
                )
            st.session_state.job_running = False
            st.rerun()
            return
        
        if "pending_audit" in st.session_state:
            audit_args = st.session_state.pop("pending_audit")
            if isinstance(audit_args, dict):
                task_id: str = str(audit_args.pop("task_id", ""))
                metrics = send_audit_request(
                    chosen_engine=cast(str, audit_args.get("chosen_engine", "")),
                    answers=cast(dict[str, str], audit_args.get("answers", {})),
                    judge_iterations=cast(int, audit_args.get("judge_iterations", 3)),
                    source_context=cast(str, audit_args.get("source_context", ""))
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
        "current_task_custom_name"
    ]
    for key in transient_keys:
        st.session_state.pop(key, None)

def _render_workspace_cleaner() -> None:
    """
    Render workspace cleaner control w/ gaurd rules
    so basically the logic to decide when to make reset the UI 
    to an original state
    """

    has_active_view: bool = bool(
        st.session_state.get("generator_report") 
        or st.session_state.get("audit_metrics")
    )
    if not has_active_view:
        return
    
    if st.button("Streamlit Workspace Reset Button", type="secondary"):
        _purge_workspace_heap()
        st.rerun()
    

def _render_step_one_upload(
    *, 
    disabled: bool,
    templates: list[str],
    models: list[str]
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

    target_document: str = st.sidebar.selectbox(
        "Chose a form template to fill out",
        templates,
        disabled=disabled,
    )

    st.header(f"1. Generate {target_document}")

    uploaded_files = st.file_uploader(
        "Drop your scientific data, READMEs, publications, ect... here:",
        accept_multiple_files=True,
        disabled=disabled,
    )

    custom_name: str = st.text_input(
        "Label this extraction run (optional):",
        placeholder="Project #1",
        disabled=disabled
    )

    if st.button("Read Files & Write Answers", type="primary", disabled=not uploaded_files or disabled):
        st.session_state.job_running = True
        st.session_state.run_state = "triggered"
        st.session_state.pending_generation = {
            "target_document": target_document,
            "chosen_engine": chosen_engine,
            "uploaded_files": uploaded_files,
            "custom_name": custom_name
        }
        st.rerun()
    return target_document

def _build_final_document_string(
    *,
    extracted_answers: dict[str, str],
    missing_questions: list[str]
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
    *,
    extracted_answers: dict[str, str],
    missing_questions: list[str]
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
    disabled: bool
) -> None:
    """
    Provides the final aggregated document for download
    """

    st.header("3. Download Final Document")

    download_format = st.radio(
        "Choose Download Format",
        options=["Markdown (.md)", "Microsoft Word (.docx)"],
        horizontal=True,
        disabled=disabled
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
            extracted_answers=extracted,
            missing_questions=missing
        )
        st.download_button(
            label="Download Document (.md)",
            data=final_markdown,
            file_name=f"{base_name}.md",
            mime="text/markdown",
            type="primary",
            disabled=disabled
        )
    else:
        final_docx: bytes = _create_docx_buffer(
            extracted_answers=extracted,
            missing_questions=missing
        )
        st.download_button(
            label="Download Document (.docx)",
            data=final_docx,
            file_name=f"{base_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            disabled=disabled
        )

def _render_generator_tab(
    *,
    is_running: bool,
    templates: list[str],
    models: list[str]
) -> None:
    """
    Renders document filling process, 
    the three step process
    """

    target_document: str = _render_step_one_upload(
        disabled=is_running,
        templates=templates,
        models=models,
    )
    
    report: dict | None = st.session_state.get("generator_report")
    if not report:
        return
    
    render_answers_and_missing_sections(disabled=is_running)
    st.markdown("---")

    missing_question: list[str] = report.get("missing_information", [])
    extracted_answers: dict[str, str] = report.get("extracted_answers", {})

    _render_step_three_download(
        target_document=target_document,
        extracted=extracted_answers,
        missing=missing_question,
        disabled=is_running
    )

    audit_metrics: dict | None = st.session_state.get("audit_metrics")
    if not audit_metrics:
        return
    
    st.markdown("---")
    st.subheader("Complete run snapshot")
    metadata: dict = audit_metrics.get("metadata", {})
    kappa_score = metadata.get("global_gwet_ac1") or metadata.get(
        "global_gwets_ac1", 0.0
    )

    st.metric("Agreement score (Gwet's AC1)", f"{float(kappa_score):.3f}")
    st.dataframe(
        audit_metrics.get("item_level_stability_metrics", []),
        use_container_width=True
    )

def _render_judge_tab(
    *, disabled: bool, models: list[str]
) -> None:
    """
    Renders the LLM Judge tab
    """

    st.header("LLM Judge: Evaluate Historical Extraction")
    st.markdown("Quantify the extraction accuracy of a past run against its original source context.")

    historical_tasks: list[dict[str, object]] = fetch_all_historical_tasks()

    completed_tasks: list[dict[str, object]] = [
        task for task in historical_tasks
        if task.get("status") == "COMPLETED" and task.get("report") is not None
    ]

    if not completed_tasks:
        st.info("No completed tasks found in database, create an extraction run first!")
        return

    # Sync selection to the currently active task
    current_task_id = st.session_state.get("current_task_id")
    if not current_task_id:
        current_task_id = str(completed_tasks[-1]["task_id"])
        st.session_state.current_task_id = current_task_id
    
    # create dictionary mapping each complete tasks full ID to human readable dropdown label
    # uses custom name, else fall back unnamed run with 8 char snippet
    task_options: dict[str, str] = {
        str(task["task_id"]): f"{task.get('custom_name') or 'Unnamed Run'} (ID: {str(task['task_id'])[:8]})"
        for task in completed_tasks 
    }

    options_keys = list(task_options.keys())
    try:
        default_index = options_keys.index(str(current_task_id))
    except ValueError:
        default_index = 0

    chosen_task_id: str = st.selectbox(
        "Select a Run to Evaluate",
        options=options_keys,
        index=default_index,
        format_func=lambda tid: task_options[tid],
        disabled=disabled
    )

    if chosen_task_id != current_task_id:
        st.session_state.current_task_id = chosen_task_id
        new_task = next(t for t in completed_tasks if str(t["task_id"]) == chosen_task_id)
        st.session_state.generator_report = new_task.get("report")
        st.session_state.source_context = new_task.get("source_context")
        st.session_state.current_task_custom_name = new_task.get("custom_name")

        custom_name = new_task.get("custom_name")
        display_name = f"{custom_name} ({chosen_task_id[:8]})" if custom_name else f"Job {chosen_task_id[:8]}"
        st.session_state.history_selectbox = display_name

        historical_audit_records = st.session_state.get("historical_audits")
        if isinstance(historical_audit_records, dict):
            st.session_state.audit_metrics = historical_audit_records.get(chosen_task_id)
        else:
            st.session_state.audit_metrics = None

        st.rerun()

    chosen_engine: str = st.selectbox("Select Evaluating AI Judge", models, disabled=disabled)

    judge_iterations: int = st.slider(
        "Testing Iterations (Higher = more accurate but much slower!)",
        min_value=2,
        max_value=10,
        value=3,
        disabled=disabled
    )

    selected_task: dict[str, object] | None = next(
        (task for task in completed_tasks if str(task["task_id"]) == chosen_task_id),
        None
    )

    if selected_task:
        st.markdown("#### Original Source Documents Under Review")
        render_trust_audit_ledger(source_context=cast(str | None, selected_task.get("source_context")))

    if st.button("Run Stability Test", type="primary", disabled=disabled):
        if not selected_task:
            return
        
        report_data = selected_task.get("report") or {}
        extracted = (
            report_data.get("extracted_answers", {})
            if isinstance(report_data, dict)
            else {}
        )

        st.session_state.job_running = True
        st.session_state.run_state = "triggered"
        st.session_state.pending_audit = {
            "task_id": chosen_task_id,
            "chosen_engine": chosen_engine,
            "judge_iterations": judge_iterations,
            "answers": extracted,
            "source_context": selected_task.get("source_context", ""),
        }
        st.rerun()
    
    audit_metrics: dict | None = st.session_state.get("audit_metrics")
    if audit_metrics:
        st.markdown("---")
        st.success("Audit complete!")

        metadata: dict = audit_metrics.get("metadata", {})
        kappa_score = metadata.get("global_gwet_ac1") or metadata.get(
            "global_gwets_ac1", 0.0
        )

        st.metric("Agreement score (Gwet's AC1)", f"{float(kappa_score):.3f}")
        st.dataframe(
            audit_metrics.get("item_level_stability_metrics", []),
            use_container_width=True,
        )

    
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
        st.warning(
            "Active AI job currently running..."
        )
    
    render_historical_sidebar()

    available_templates: list[str] = fetch_server_templates()
    available_models: list[str] = list(MODEL_CONFIGURATIONS.keys())

    tab_generator, tab_judge = st.tabs(
        ["Document Generator", "LLM Judge Evaluation"]
    )

    with tab_generator:
        _render_generator_tab(
            is_running=is_running,
            templates=available_templates,
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
"""
Primary streamlit rendering
"""

import logging
from typing import Final, cast

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
            generation_args: dict[str, object] = st.session_state.pop("pending_generation")
            send_generation_request(
                target_document=cast(str, generation_args["target_document"]),
                chosen_engine=cast(str, generation_args["chosen_engine"]),
                uploaded_files=cast(list[UploadedFileProtocol], generation_args["uploaded_files"]),
                custom_name=cast(str, generation_args.get("custom_name", ""))
            )
            st.session_state.job_running = False
            st.rerun()
            return
        
        if "pending_audit" in st.session_state:
            audit_args: dict[str, object] = st.session_state.pop("pending_audit")
            task_id: str = str(audit_args.pop("task_id", ""))
            metrics = send_audit_request(
                chosen_engine=cast(str, audit_args["chosen_engine"]),
                answers=cast(dict[str, str], audit_args["answers"]),
                judge_iterations=cast(int, audit_args["judge_iterations"]),
                source_context=cast(str, audit_args["source_context"])
            )
            if metrics:
                st.session_state.audit_metrics = metrics

                if "historical_audits" not in st.session_state:
                    st.session_state.historical_audits = {}
                st.session_state.historical_audits[task_id] = metrics

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
        "current_task_id"
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

def _render_step_two_manual_entry(*, missing_questions: list[str], disabled: bool) -> None:
    """
    Dynamically renders forms for users to fill AI-missed fields.
    """

    st.header("2. Add Additional Information")

    if not missing_questions:
        st.success("The AI successfully answered all questions! No additional info needed.")
        return
    
    st.info(f"The AI missed {len(missing_questions)} question(s). You may optionally provide answers below:")

    with st.form("manual_entry_form"):
        for question in missing_questions:
            st.text_area(label=question, key=f"manual_{question}", disabled=disabled)

        if st.form_submit_button("Save Optional Responses", disabled=disabled):
            st.success("Responses saved! You can generate your document below.")

def _build_final_document_string(
    *,
    extracted: dict[str, str],
    missing: list[str]
) -> str:
    """
    Aggregates text chunks
    """

    document_blocks: list[str] = ["# Final Extracted Document\n\n"]

    for question, answer in extracted.items():
        document_blocks.append(f"### {question}\n{answer}\n\n")
    
    for question in missing:
        manual_answer: str = str(st.session_state.get(f"manual_{question}", "")).strip()
        if not manual_answer:
            document_blocks.append(f"### {question}\n*No answer provided*\n\n")
        else:
            document_blocks.append(f"### {question}\n{manual_answer}\n\n")

    return "".join(document_blocks)


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

    final_markdown: str = _build_final_document_string(extracted=extracted, missing=missing)

    st.download_button(
        label="Download Document (.md)",
        data=final_markdown,
        file_name=f"{target_document}_completed.md",
        mime="text/markdown",
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
    
    render_answers_and_missing_sections()
    st.markdown("---")

    missing_question: list[str] = report.get("missing_information", [])
    extracted_answers: dict[str, str] = report.get("extracted_answers", {})

    _render_step_two_manual_entry(missing_questions=missing_question, disabled=is_running)
    st.markdown("---")

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
    
    # create dictionary mapping each complete tasks full ID to human readable dropdown label
    # uses custom name, else fall back unnamed run with 8 char snippet
    task_options: dict[str, str] = {
        str(task["task_id"]): f"{task.get('custom_name') or 'Unnamed Run'} (ID: {str(task['task_id'])[:8]})"
        for task in completed_tasks 
    }

    chosen_task_id: str = st.selectbox(
        "Select a Run to Evaluate",
        options=list(task_options.keys()),
        format_func=lambda tid: task_options[tid],
        disabled=disabled
    )

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
        current_task_id: str | None = st.session_state.get("current_task_id")
        if current_task_id == chosen_task_id:
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
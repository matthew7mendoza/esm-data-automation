"""
Primary streamlit rendering — single linear 3-step pipeline.
"""

import io
import logging
from typing import Final, cast

import streamlit as st
from docx import Document

from frontend.api import fetch_server_templates
from frontend.components.extraction_hub import render_extraction_hub
from frontend.components.sidebar import render_historical_sidebar
from frontend.config import MODEL_CONFIGURATIONS
from frontend.protocols import UploadedFileProtocol
from frontend.services import send_audit_request, send_generation_request

__all__ = ["main"]

logger: Final[logging.Logger] = logging.getLogger(__name__)

# 4-step progress milestones mirroring batch_queue labels
_PIPELINE_MILESTONES: Final[list[str]] = [
    "Reading Files…",
    "LLM Extraction…",
    "Validation…",
    "Completed",
]


def _initialize_session_state() -> None:
    """
    Set up core streamlit session with explicit mutation.
    `is_processing` is the canonical mutual-exclusion guard that freezes
    the entire widget canvas while the backend pipeline executes.
    """

    defaults: dict[str, bool | dict[str, object] | str | None] = {
        "generator_report": None,
        "source_context": None,
        "audit_metrics": None,
        "job_running": False,
        "is_processing": False,
        "current_task_id": None,
        "current_task_custom_name": None,
        "historical_audits": {},
        "run_state": "idle",
        "pipeline_step": 0,
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
    st.session_state.pipeline_step = 4
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
        metrics["task_id"] = task_id
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
    Executes queued background tasks then refreshes the app.
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
    to baseline so things don't get messy.
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
    st.session_state.pipeline_step = 0


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


def _render_sidebar_config(
    *, templates: list[str], models: list[str]
) -> tuple[str, str]:
    """
    Declarative sidebar manager for all data ingestion options and
    configuration selectors. Bundled inside a collapsible expander so
    the sidebar remains compact. Isolated from the global canvas so it
    stays stable while results are displayed.
    """

    is_locked: bool = bool(st.session_state.get("is_processing"))

    with st.sidebar:
        st.title("Run Configuration")
        st.markdown("---")

        with st.expander("⚙️ Model & Template", expanded=True):
            chosen_engine: str = st.selectbox(
                "Select AI Model",
                models,
                disabled=is_locked,
                key="step1_model",
            )

            target_document: str = st.selectbox(
                "Choose a form template to fill out",
                templates,
                disabled=is_locked,
                key="step1_template",
            )

    return cast(str, chosen_engine), cast(str, target_document)


def _render_step_one_upload(
    *,
    disabled: bool,
    chosen_engine: str,
    target_document: str,
) -> None:
    """
    Step 1: file uploader and the primary action button.
    Configuration dropdowns live in the sidebar (see _render_sidebar_config).
    """

    uploaded_files = st.file_uploader(
        "Drop your scientific data, READMEs, publications, etc. here:",
        accept_multiple_files=True,
        disabled=disabled,
    )

    custom_name: str = st.text_input(
        "Label this extraction run (optional):",
        placeholder="Project #1",
        disabled=disabled,
    )

    submit_ready: bool = bool(uploaded_files) and not disabled
    if st.button(
        "Read Files & Write Answers",
        type="primary",
        disabled=not submit_ready,
    ):
        # Phase 3: flip the lock first so the next render sees a frozen canvas,
        # then queue all deferred-execution state before the rerun.
        st.session_state.is_processing = True
        st.session_state.job_running = True
        st.session_state.run_state = "triggered"
        st.session_state.pipeline_step = 1
        st.session_state.pending_generation = {
            "target_document": target_document,
            "chosen_engine": chosen_engine,
            "uploaded_files": uploaded_files,
            "custom_name": custom_name,
        }
        st.rerun()


def _render_step_two_progress() -> None:
    """
    Step 2a: live progress bar shown while job_running is True.
    Cycles through the 4 pipeline milestones on each rerun.
    """

    pipeline_step: int = int(st.session_state.get("pipeline_step", 1))
    clamped_step = max(1, min(pipeline_step, len(_PIPELINE_MILESTONES)))
    progress_val = clamped_step / len(_PIPELINE_MILESTONES)
    label = _PIPELINE_MILESTONES[clamped_step - 1]

    st.progress(progress_val, text=f"**{label}**")

    # Advance the displayed milestone each rerun while the job runs
    next_step = clamped_step + 1 if clamped_step < len(_PIPELINE_MILESTONES) else clamped_step
    st.session_state.pipeline_step = next_step


def _build_final_document_string(
    *, extracted_answers: dict[str, str], missing_questions: list[str]
) -> str:
    """
    Aggregates text chunks.
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
    Provides the final aggregated document for download.
    The `disabled` flag is bound to `is_processing` so download controls
    are frozen during active pipeline execution.
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


def _render_audit_dataframe(audit_metrics: dict[str, object]) -> None:
    """
    Renders the LLM Judge results dataframe inline below the extraction hub.
    """
    st.markdown("---")
    st.subheader("LLM Judge — Run Snapshot")

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


def main() -> None:
    """
    Main control flow — single linear 3-step pipeline.
    Widget interlock is driven exclusively by `is_processing` so there is
    a single source of truth for the frozen-canvas invariant.
    """

    st.set_page_config(page_title="ESM Data Automation", layout="wide")
    st.title("ESM Data Automation Pipeline")

    _initialize_session_state()

    # Phase 3: defensive boundary around the entire pending-job dispatcher.
    try:
        with st.spinner("Executing data automation pipeline..."):
            _process_pending_jobs()
    except ValueError as ve:
        st.error(f"Data format mismatch: {ve}")
    except Exception as e:
        st.error(f"Pipeline Interrupted: {str(e)}")
    finally:
        # Only release the lock if a job that set it has finished running.
        job_still_running: bool = bool(st.session_state.get("job_running"))
        if not job_still_running:
            st.session_state.is_processing = False

    is_processing: bool = bool(st.session_state.get("is_processing"))
    is_running: bool = bool(st.session_state.get("job_running"))

    available_templates: list[str] = fetch_server_templates()
    available_models: list[str] = list(MODEL_CONFIGURATIONS.keys())

    # Sidebar: isolated Run Configuration panel + historical navigation.
    chosen_engine, target_document = _render_sidebar_config(
        templates=available_templates,
        models=available_models,
    )
    render_historical_sidebar()
    _render_workspace_cleaner()

    # ── Step 1 ────────────────────────────────────────────────────────────────
    st.header("1. Configure & Upload")
    _render_step_one_upload(
        disabled=is_processing,
        chosen_engine=chosen_engine,
        target_document=target_document,
    )

    # ── Step 2 ────────────────────────────────────────────────────────────────
    if is_running:
        st.markdown("---")
        st.header("2. Processing…")
        _render_step_two_progress()

        if st.session_state.get("run_state") == "executing":
            st.rerun()
        return

    report = cast(dict[str, object] | None, st.session_state.get("generator_report"))
    if not report:
        return

    render_extraction_hub(disabled=is_processing)

    audit_metrics = cast(
        dict[str, object] | None, st.session_state.get("audit_metrics")
    )
    if audit_metrics:
        _render_audit_dataframe(audit_metrics)

    # ── Step 3 ────────────────────────────────────────────────────────────────
    st.markdown("---")

    missing_questions: list[str] = cast(
        list[str], report.get("missing_information", [])
    )
    extracted_answers: dict[str, str] = cast(
        dict[str, str], report.get("extracted_answers", {})
    )

    _render_step_three_download(
        target_document=target_document,
        extracted=extracted_answers,
        missing=missing_questions,
        disabled=is_processing,
    )


if __name__ == "__main__":
    main()

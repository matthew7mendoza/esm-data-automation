"""
Assemble the complete application
"""

import logging
import os
from typing import Final, cast

import streamlit as st

from frontend.api import fetch_server_templates
from frontend.components.sidebar import (
    render_historical_sidebar,
)
from frontend.config import (
    MODEL_CONFIGURATIONS,
    TEMPLATE_DISPLAY_NAMES,
)
from frontend.protocols import UploadedFileProtocol
from frontend.services import send_audit_request, send_generation_request
from frontend.views.generator import render_generator_tab_view
from frontend.views.judge import render_judge_tab_view
from frontend.views.overview import render_overview_view

__all__ = ["main"]

logger: Final[logging.Logger] = logging.getLogger(__name__)
OVERVIEW_PAGE: Final[str] = "OVERVIEW"


def inject_global_theme() -> None:
    """Reads static layout styles and binds them directly into the runtime view."""
    css_path = os.path.join(os.path.dirname(__file__), "assets", "styles.css")
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def _initialize_session_state() -> None:
    """Sets up primary runtime memory allocations safely."""
    defaults: dict[str, bool | dict[str, object] | str | None] = {
        "generator_report": None,
        "source_context": None,
        "audit_metrics": None,
        "job_running": False,
        "current_task_id": None,
        "current_task_custom_name": None,
        "historical_audits": {},
        "run_state": "idle",
        "selected_template": OVERVIEW_PAGE,
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
    st.session_state.job_running = False
    if not metrics:
        st.rerun()
        return

    st.session_state.audit_metrics = metrics
    historical_audits = st.session_state.get("historical_audits")
    if not isinstance(historical_audits, dict):
        historical_audits = {}
    historical_audits[task_id] = metrics
    st.session_state.historical_audits = historical_audits
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
    """Executes queued background tasks then refreshes the app."""
    if not _should_execute_pending_job():
        return

    if "pending_generation" in st.session_state:
        _handle_pending_generation(st.session_state.pop("pending_generation"))
        return

    if "pending_audit" in st.session_state:
        _handle_pending_audit(st.session_state.pop("pending_audit"))
        return


def _render_template_button(
    template_name: str, selected_page: str, disabled: bool
) -> None:
    btn_label = TEMPLATE_DISPLAY_NAMES.get(template_name, template_name)
    is_active = template_name == selected_page
    clicked = st.sidebar.button(
        btn_label,
        key=f"template_page_{template_name}",
        type="primary" if is_active else "secondary",
        width="stretch",
        disabled=disabled,
    )
    if not clicked:
        return
    st.session_state.selected_template = template_name
    st.rerun()


def _render_sidebar_navigation(*, disabled: bool, templates: list[str]) -> str:
    """Renders the sidebar page navigation."""
    selected_page: str = st.session_state.get("selected_template", OVERVIEW_PAGE)
    is_invalid = selected_page != OVERVIEW_PAGE and selected_page not in templates
    if is_invalid:
        selected_page = OVERVIEW_PAGE
        st.session_state.selected_template = selected_page

    for template_name in templates:
        _render_template_button(template_name, selected_page, disabled)

    return selected_page


def _render_active_run_header(currently_active_task_id: str | None) -> None:
    if not currently_active_task_id:
        return

    task_custom_name = st.session_state.get("current_task_custom_name")
    short_task_id = str(currently_active_task_id)[:8]
    custom_name = task_custom_name or f"Job {short_task_id}"
    st.markdown(f"### Active Run: **{custom_name}**")


def _render_sidebar(
    is_running: bool,
    available_templates: list[str],
    available_models: list[str],
) -> str:
    """Renders the sidebar navigation and returns the selected page."""
    selected_page: str = st.session_state.get("selected_template", OVERVIEW_PAGE)
    is_invalid = (
        selected_page != OVERVIEW_PAGE and selected_page not in available_templates
    )
    if is_invalid:
        selected_page = OVERVIEW_PAGE
        st.session_state.selected_template = selected_page

    overview_clicked = st.sidebar.button(
        "Overview",
        key="page_overview",
        type="primary" if selected_page == OVERVIEW_PAGE else "secondary",
        width="stretch",
        disabled=is_running,
    )
    if overview_clicked:
        st.session_state.selected_template = OVERVIEW_PAGE
        st.rerun()

    # Form Templates Section Title
    st.sidebar.markdown(
        "<div style='font-size: 0.75rem; font-weight: 700; "
        "letter-spacing: 0.05em; color: #6b7280; text-transform: uppercase; "
        "margin-top: 1.5rem; margin-bottom: 0.5rem; padding-left: 12px;'>"
        "Form Templates</div>",
        unsafe_allow_html=True,
    )

    selected_page = _render_sidebar_navigation(
        disabled=is_running,
        templates=available_templates,
    )

    # Consolidated Session Management is rendered next
    render_historical_sidebar()

    # Settings Section Title
    st.sidebar.markdown(
        "<div style='font-size: 0.75rem; font-weight: 700; "
        "letter-spacing: 0.05em; color: #6b7280; text-transform: uppercase; "
        "margin-top: 2rem; margin-bottom: 0.5rem; padding-left: 12px;'>"
        "Settings</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.selectbox(
        "Select AI Model",
        available_models,
        disabled=is_running,
        key="global_chosen_engine",
    )
    return selected_page


def main() -> None:
    """Core coordination routine. Targets low indentation depths via guard clauses."""
    st.set_page_config(page_title="ESM Data Automation", layout="wide")

    inject_global_theme()
    st.title("ESM Data Automation Pipeline")

    _initialize_session_state()
    _process_pending_jobs()

    is_running: bool = bool(st.session_state.get("job_running"))

    if is_running:
        st.warning("Active AI job currently running...")

    available_templates: list[str] = fetch_server_templates()
    available_models: list[str] = list(MODEL_CONFIGURATIONS.keys())
    selected_page: str = _render_sidebar(
        is_running, available_templates, available_models
    )

    if selected_page == OVERVIEW_PAGE:
        render_overview_view()
        return

    # Main Workspace header area
    currently_active_task_id = st.session_state.get("current_task_id")
    _render_active_run_header(currently_active_task_id)

    tab_generator, tab_judge = st.tabs(["Document Generator", "LLM Judge Evaluation"])

    with tab_generator:
        render_generator_tab_view(
            disabled=is_running,
            target_document=selected_page,
        )

    with tab_judge:
        render_judge_tab_view(
            disabled=is_running,
            models=available_models,
        )

    if st.session_state.get("run_state") == "executing":
        st.rerun()


if __name__ == "__main__":
    main()

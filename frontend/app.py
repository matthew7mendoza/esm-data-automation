"""
Assemble the complete application
"""

import logging
import os
from typing import Final

import streamlit as st

from frontend.client import fetch_server_templates
from frontend.components.sidebar import (
    render_historical_sidebar,
)
from frontend.ui_constants import (
    MODEL_CONFIGURATIONS,
    TEMPLATE_DISPLAY_NAMES,
)
from frontend.views.generator import render_generator_tab_view
from frontend.views.judge import render_judge_tab_view
from frontend.views.overview import render_overview_view
from frontend.views.review import render_review_view
from frontend.views.settings import _fetch_active_settings, render_settings_view
from frontend.views.tracker import render_tracker_view

__all__ = ["main"]

logger: Final[logging.Logger] = logging.getLogger(__name__)
OVERVIEW_PAGE: Final[str] = "OVERVIEW"
SETTINGS_PAGE: Final[str] = "SETTINGS"
TRACKER_PAGE: Final[str] = "TRACKER"
REVIEW_PAGE: Final[str] = "REVIEW"


def inject_global_theme() -> None:
    """Reads static layout styles and binds them directly into the runtime view."""
    css_path = os.path.join(os.path.dirname(__file__), "assets", "styles.css")
    with open(css_path, encoding="utf-8") as file_handle:
        st.markdown(f"<style>{file_handle.read()}</style>", unsafe_allow_html=True)


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

    if "available_models" not in st.session_state:
        st.session_state.available_models = list(MODEL_CONFIGURATIONS.keys())

    is_not_set = "global_chosen_engine" not in st.session_state
    has_models = st.session_state.available_models
    if is_not_set and has_models:
        st.session_state.global_chosen_engine = st.session_state.available_models[0]


def _on_template_selected() -> None:
    is_job_currently_running: bool = bool(
        st.session_state.get("job_running") or st.session_state.get("is_extracting")
    )
    if is_job_currently_running:
        return

    new_selected_template: str | None = st.session_state.get("template_selectbox")
    if new_selected_template is None:
        return

    st.session_state.selected_template = new_selected_template


def _render_sidebar_navigation(*, disabled: bool, templates: list[str]) -> str:
    selected_page: str = st.session_state.get("selected_template", OVERVIEW_PAGE)
    is_invalid = (
        selected_page != OVERVIEW_PAGE
        and selected_page != SETTINGS_PAGE
        and selected_page != TRACKER_PAGE
        and selected_page not in templates
    )
    if is_invalid:
        selected_page = OVERVIEW_PAGE
        st.session_state.selected_template = selected_page

    if templates:
        current_index = 0
        if selected_page in templates:
            current_index = templates.index(selected_page)

        st.sidebar.selectbox(
            "Select Template",
            options=templates,
            index=current_index,
            format_func=lambda t: TEMPLATE_DISPLAY_NAMES.get(t, t),
            disabled=disabled,
            key="template_selectbox",
            on_change=_on_template_selected,
        )

    return selected_page


def _render_active_run_header(currently_active_task_id: str | None) -> None:
    if not currently_active_task_id:
        return

    task_custom_name = st.session_state.get("current_task_custom_name")
    short_task_id = str(currently_active_task_id)[:8]
    custom_name = task_custom_name or f"Job {short_task_id}"
    st.markdown(f"### Active Run: **{custom_name}**")


def _render_sidebar(  # noqa: C901
    is_running: bool,
    available_templates: list[str],
) -> str:
    """Renders the sidebar navigation and returns the selected page."""
    selected_page: str = st.session_state.get("selected_template", OVERVIEW_PAGE)
    is_invalid = (
        selected_page != OVERVIEW_PAGE
        and selected_page != SETTINGS_PAGE
        and selected_page != TRACKER_PAGE
        and selected_page not in available_templates
    )
    if is_invalid:
        selected_page = OVERVIEW_PAGE
        st.session_state.selected_template = selected_page

    if selected_page in (OVERVIEW_PAGE, TRACKER_PAGE):
        return selected_page

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

    selected_page = _render_sidebar_navigation(
        disabled=is_running,
        templates=available_templates,
    )

    render_historical_sidebar(disabled=is_running)

    st.sidebar.markdown(
        "<div style='font-size: 0.75rem; font-weight: 700; "
        "letter-spacing: 0.05em; color: #6b7280; text-transform: uppercase; "
        "margin-top: 2rem; margin-bottom: 0.5rem; padding-left: 12px;'>"
        "Settings</div>",
        unsafe_allow_html=True,
    )

    settings_clicked = st.sidebar.button(
        "System Settings & Customization",
        key="page_settings_navigation",
        type="primary" if selected_page == SETTINGS_PAGE else "secondary",
        width="stretch",
        disabled=is_running,
    )
    if settings_clicked:
        st.session_state.selected_template = SETTINGS_PAGE
        st.rerun()

    if settings_clicked:
        return SETTINGS_PAGE
    return selected_page


def main() -> None:  # noqa: C901
    """Core coordination routine. Targets low indentation depths via guard clauses."""
    st.set_page_config(
        page_title="ESM Data Automation",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    inject_global_theme()

    _initialize_session_state()
    is_running: bool = bool(st.session_state.get("is_extracting"))

    if is_running:
        st.warning("Active AI job currently running...")

    available_templates: list[str] = fetch_server_templates()
    available_models: list[str] = list(st.session_state.available_models)

    if "local_config_state" not in st.session_state:
        fetched = _fetch_active_settings()
        if fetched:
            st.session_state.local_config_state = fetched

    task_id_query = st.query_params.get("task_id")
    if task_id_query:
        st.session_state.current_task_id = task_id_query
        st.session_state.selected_template = REVIEW_PAGE
        st.query_params.clear()

    if st.session_state.get("selected_template") == REVIEW_PAGE:
        selected_page = REVIEW_PAGE
    else:
        selected_page = _render_sidebar(is_running, available_templates)

    if selected_page == REVIEW_PAGE:
        render_review_view(disabled=is_running)
        return

    if selected_page == SETTINGS_PAGE:
        render_settings_view(disabled=is_running)
        return

    st.title("ESM Data Automation Pipeline")

    if selected_page == OVERVIEW_PAGE:
        render_overview_view(disabled=is_running)
        return

    if selected_page == TRACKER_PAGE:
        render_tracker_view(disabled=is_running)
        return

    currently_active_task_id = st.session_state.get("current_task_id")
    _render_active_run_header(currently_active_task_id)

    generator_navigation_tab, judge_evaluation_navigation_tab = st.tabs(
        ["Document Generator", "LLM Judge Evaluation"],
        key="main_workflow_navigation_tabs",
    )

    with generator_navigation_tab:
        render_generator_tab_view(
            disabled=is_running,
            target_document=selected_page,
        )

    with judge_evaluation_navigation_tab:
        render_judge_tab_view(
            disabled=is_running,
            models=available_models,
        )

    if st.session_state.get("run_state") == "executing":
        st.rerun()


if __name__ == "__main__":
    main()

"""
Side-by-side extraction hub: Verification Ledger (left)
and Source Artifact Viewer (right). Answers are staged directly
in Streamlit widget state under deterministic keys and committed
to the database atomically only when the user clicks "Save Changes".
"""


import re
from collections.abc import Callable
from typing import cast

import streamlit as st

from frontend.api import update_task_report
from frontend.components.stability_ribbon import render_stability_ribbon

__all__ = ["render_extraction_hub"]

_DRAFT_KEY = "drafts"
_FOCUS_KEY = "active_focus_field"


def _draft_widget_key(task_id: str, question: str) -> str:
    """Deterministic Streamlit widget key for a draft text area."""
    return f"draft_val_{task_id}_{question}"


def _ensure_drafts_initialized(
    task_id: str,
    extracted_answers: dict[str, str],
    missing_information: list[str],
) -> None:
    """
    Populates st.session_state.drafts from the current report the first time
    a task is loaded, or whenever the active task changes.
    """

    drafts: dict[str, object] = st.session_state.setdefault(_DRAFT_KEY, {})
    stored_task_id = drafts.get("__task_id__")

    task_unchanged = stored_task_id == task_id
    if task_unchanged:
        return

    all_questions: dict[str, str] = {**extracted_answers}
    for question in missing_information:
        all_questions.setdefault(question, "")

    drafts.clear()
    drafts["__task_id__"] = task_id
    drafts.update(all_questions)


def _commit_drafts_to_db(task_id: str, all_questions: list[str]) -> bool:
    """
    Reads widget state directly via deterministic draft_val_ keys,
    splits into extracted/missing buckets, and sends a single PATCH call.
    Returns True on success.
    """

    updated_extracted: dict[str, str] = {}
    updated_missing: list[str] = []

    for question in all_questions:
        widget_key = _draft_widget_key(task_id, question)
        raw = st.session_state.get(widget_key, "")
        text = str(raw).strip()

        answer_is_blank = not text
        if answer_is_blank:
            updated_missing.append(question)
            continue

        updated_extracted[question] = text

    success = update_task_report(
        task_id=task_id,
        extracted_answers=updated_extracted,
        missing_information=updated_missing,
    )

    if not success:
        return False

    new_report = {
        "extracted_answers": updated_extracted,
        "missing_information": updated_missing,
    }
    st.session_state.generator_report = new_report
    return True


def _make_focus_callback(question: str) -> Callable[[], None]:
    """Returns an on_change callback that records which field is active."""

    def _set_focus() -> None:
        st.session_state[_FOCUS_KEY] = question

    return _set_focus


def _stability_badge(r_stab: float | None) -> str:
    """
    Returns a small coloured emoji badge string based on the r_stab score.
    Green ≥ 0.7, yellow ≥ 0.4, red otherwise. Returns empty string when absent.
    """
    if r_stab is None:
        return ""
    if r_stab >= 0.7:
        return f" 🟢 {r_stab:.2f}"
    if r_stab >= 0.4:
        return f" 🟡 {r_stab:.2f}"
    return f" 🔴 {r_stab:.2f}"


def _build_stability_index(
    audit_metrics: dict[str, object] | None,
) -> dict[str, float]:
    """
    Extracts a {question: r_stab} mapping from audit_metrics
    item_level_stability_metrics list, keyed by 'question'.
    Returns an empty dict when no metrics are present.
    """
    if not isinstance(audit_metrics, dict):
        return {}

    items = audit_metrics.get("item_level_stability_metrics")
    if not isinstance(items, list):
        return {}

    index: dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        r_stab = item.get("reasoning_stability_r_stab")
        if isinstance(question, str) and isinstance(r_stab, (int, float)):
            index[question] = float(r_stab)
    return index


def _render_question_input(
    *,
    task_id: str,
    question: str,
    extracted_answers: dict[str, str],
    missing_information: list[str],
    disabled: bool,
    stability_index: dict[str, float],
) -> None:
    """Helper to render a single question text area in the ledger."""
    widget_key = _draft_widget_key(task_id, question)
    initial_value = extracted_answers.get(question, "")
    st.session_state.setdefault(widget_key, initial_value)

    is_missing = (
        question in missing_information
        and not extracted_answers.get(question, "").strip()
    )
    prefix = "Missing: " if is_missing else ""
    badge = _stability_badge(stability_index.get(question))
    label = f"{prefix}{question}{badge}"

    st.text_area(
        label=label,
        key=widget_key,
        disabled=disabled,
        height=100,
        on_change=_make_focus_callback(question),
    )


def _render_ledger_items(
    *,
    task_id: str,
    all_questions: list[str],
    extracted_answers: dict[str, str],
    missing_information: list[str],
    disabled: bool,
    stability_index: dict[str, float],
) -> None:
    """Helper to render all text areas inside the ledger container."""
    for question in all_questions:
        _render_question_input(
            task_id=task_id,
            question=question,
            extracted_answers=extracted_answers,
            missing_information=missing_information,
            disabled=disabled,
            stability_index=stability_index,
        )


def _render_verification_ledger(
    task_id: str,
    extracted_answers: dict[str, str],
    missing_information: list[str],
    disabled: bool,
    active_task_data: dict[str, object],
) -> None:
    """
    Left pane: scrollable list of question/answer text areas.
    Each widget key is the canonical draft_val_ path in Streamlit widget state.
    on_change sets active_focus_field so the right pane can highlight context.
    A single Save Changes button commits all fields atomically.
    Inline accuracy badges are shown per-question when audit_metrics exist.
    """

    st.subheader("Verification Ledger")
    st.caption("Edit answers below, then click **Save Changes** to persist.")

    render_stability_ribbon(
        task_id=task_id,
        active_task_data=active_task_data,
        disabled=disabled,
    )

    audit_metrics = cast(
        dict[str, object] | None, st.session_state.get("audit_metrics")
    )
    stability_index = _build_stability_index(audit_metrics)

    all_questions: list[str] = list(extracted_answers.keys())
    new_questions = [q for q in missing_information if q not in all_questions]
    all_questions.extend(new_questions)

    ledger_container = st.container(height=620, border=False)
    with ledger_container:
        _render_ledger_items(
            task_id=task_id,
            all_questions=all_questions,
            extracted_answers=extracted_answers,
            missing_information=missing_information,
            disabled=disabled,
            stability_index=stability_index,
        )

    st.markdown("---")

    save_col, _ = st.columns([1, 3])
    with save_col:
        save_clicked = st.button(
            "Save Changes",
            type="primary",
            disabled=disabled,
            use_container_width=True,
        )

    if not save_clicked:
        return

    success = _commit_drafts_to_db(task_id=task_id, all_questions=all_questions)
    if not success:
        st.error("Failed to save changes to backend database.")
        return

    st.toast("Changes saved successfully!")
    st.rerun()


def _inject_highlight(source_context: str, focus_term: str) -> str:
    """
    Wraps every occurrence of focus_term in the source context with
    an HTML mark tag using a soft yellow background.
    Operates on a safe escaped copy so existing markdown is preserved.
    """

    term_is_blank = not focus_term.strip()
    if term_is_blank:
        return source_context

    escaped_term = re.escape(focus_term.strip())
    highlight_tag = r'<mark style="background-color: rgba(255, 235, 59, 0.3);">'
    replacement = rf"{highlight_tag}\g<0></mark>"
    return re.sub(escaped_term, replacement, source_context, flags=re.IGNORECASE)


def _render_source_artifact_viewer(source_context: str | None) -> None:
    """
    Right pane: scrollable markdown display of the raw source context.
    When active_focus_field is set (by a ledger text area on_change),
    the matching term is highlighted with a translucent yellow mark tag.
    """

    st.subheader("Source Artifact Viewer")
    st.caption("The original source documents used for this extraction run.")

    if not source_context:
        st.info("No source context available for this run.")
        return

    active_field: str | None = st.session_state.get(_FOCUS_KEY)
    display_context = source_context

    field_is_active = bool(active_field)
    if field_is_active:
        display_context = _inject_highlight(
            source_context=source_context,
            focus_term=cast(str, active_field),
        )

    artifact_container = st.container(height=700, border=True)
    with artifact_container:
        st.markdown(display_context, unsafe_allow_html=True)


def render_extraction_hub(*, disabled: bool = False) -> None:
    """
    Renders the full side-by-side extraction hub panel.
    Guards on required session state; exits early if data is absent.
    """

    current_task_id: str | None = st.session_state.get("current_task_id")
    report: object = st.session_state.get("generator_report")

    missing_task = not current_task_id
    missing_report = not isinstance(report, dict)
    if missing_task or missing_report:
        return

    task_id = str(current_task_id)
    report_dict = cast(dict[str, object], report)

    extracted_answers: dict[str, str] = cast(
        dict[str, str], report_dict.get("extracted_answers") or {}
    )
    missing_information: list[str] = cast(
        list[str], report_dict.get("missing_information") or []
    )
    source_context: str | None = cast(
        str | None, st.session_state.get("source_context")
    )

    _ensure_drafts_initialized(
        task_id=task_id,
        extracted_answers=extracted_answers,
        missing_information=missing_information,
    )

    st.header("2. Review & Edit Answers")

    left_col, right_col = st.columns([1, 1])

    active_task_data: dict[str, object] = {
        "report": report_dict,
        "source_context": source_context or "",
    }

    with left_col:
        _render_verification_ledger(
            task_id=task_id,
            extracted_answers=extracted_answers,
            missing_information=missing_information,
            disabled=disabled,
            active_task_data=active_task_data,
        )

    with right_col:
        _render_source_artifact_viewer(source_context=source_context)

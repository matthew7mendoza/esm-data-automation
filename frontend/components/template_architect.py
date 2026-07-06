"""
Template Architect View Component.
Dual-pane layout with Option A (manual fields) and Option B (upload area) on the left,
and inferred cards in stabilized placeholders on the right.
"""

from typing import Final

import streamlit as st

__all__ = ["render_template_architect"]

_NUM_SLOTS: Final[int] = 5


def _render_left_pane() -> None:
    """Renders Option A manual fields and Option B upload area."""
    st.subheader("Schema Source")

    st.markdown("#### Option A: Manual Field List")
    st.text_area(
        "Enter fields (one per line):",
        value=(
            "Patient Name\nDate of Birth\n"
            "Clinical Diagnosis\nLab Results\n"
            "Recommended Treatment"
        ),
        key="ta_manual_fields",
        height=150,
    )

    st.markdown("#### Option B: Form Document Upload")
    st.file_uploader(
        "Upload a sample form to infer fields:",
        key="ta_sample_file",
        help="Supports .txt, .md, .docx, or PDF forms",
    )

    st.button(
        "Infer & Architect Schema",
        key="ta_infer_schema_btn",
        type="primary",
        use_container_width=True,
    )


def _populate_inferred_card(
    slot: st.delta_generator.DeltaGenerator, fields: list[str], idx: int
) -> None:
    """Populates an empty slot with an inferred card or fallback warning."""
    is_out_of_bounds = idx >= len(fields)
    if is_out_of_bounds:
        slot.warning(f"Card Slot #{idx + 1}: Unused template slot", icon="⚠️")
        return

    field_name = fields[idx]
    with slot.container(border=True):
        st.markdown(f"**Field #{idx + 1}: {field_name}**")
        st.caption(f"Inferred Type: `string` | Key: `field_{idx + 1}`")
        st.text_input(
            f"Override label for Field #{idx + 1}",
            value=field_name,
            key=f"ta_field_override_{idx}",
        )


def _show_awaiting_state(slots: list[st.delta_generator.DeltaGenerator]) -> None:
    """Fills empty slots with awaiting instruction state."""
    for idx, slot in enumerate(slots):
        slot.info(f"Card Slot #{idx + 1}: Awaiting template inference...", icon="⏳")


def _render_right_pane() -> None:
    """Renders inferred cards using st.empty() slots to stabilize loading state."""
    st.subheader("Inferred Schema Cards")
    st.caption("Stabilized placeholders update dynamically when schema is inferred.")

    # Pre-allocate empty slots
    slots = [st.empty() for _ in range(_NUM_SLOTS)]

    infer_clicked = st.session_state.get("ta_infer_schema_btn", False)
    if not infer_clicked:
        _show_awaiting_state(slots)
        return

    manual_fields_str = st.session_state.get("ta_manual_fields", "")
    fields = [f.strip() for f in manual_fields_str.split("\n") if f.strip()]

    for idx, slot in enumerate(slots):
        _populate_inferred_card(slot, fields, idx)


def render_template_architect() -> None:
    """Primary entry point for Template Architect view."""
    st.header("Template Architect")
    st.markdown(
        "Define extraction schemas manually or infer them from existing documents."
    )

    left_col, right_col = st.columns([1, 1])

    with left_col:
        _render_left_pane()

    with right_col:
        _render_right_pane()

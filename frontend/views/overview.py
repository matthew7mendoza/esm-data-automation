"""
Overview landing page view rendering features and guides.
"""

import streamlit as st

__all__ = ["render_overview_view"]


def render_overview_view(*, disabled: bool) -> None:
    """
    Renders landing page details and template starter triggers.
    """
    st.markdown(
        """
        <div style="margin-top: 1rem; margin-bottom: 2rem;">
            <h1 style="font-size: 2.5rem; font-weight: 800;
                background: linear-gradient(95deg, #2563eb, #3b82f6, #1d4ed8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent; margin-bottom: 0.5rem;">
                ESM Data Automation Pipeline
            </h1>
            <p style="font-size: 1.1rem; color: #4b5563; line-height: 1.6;
                max-width: 800px;">
                Accelerate scientific data stewardship. Extract structured
                metadata and build high-quality dataset documentation
                directly from your workflow.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Select Your Workflow")

    column_one, column_two = st.columns(2)

    with column_one:
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 12px; padding: 20px; margin-bottom: 20px;
                height: 220px; transition: transform 0.2s ease;">
                <h4 style="margin-top: 0; color: #1e3a8a; display: flex;
                    align-items: center; gap: 8px;">
                    Start a New Experiment (Metadata Tracker)
                </h4>
                <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;
                    margin-bottom: 0;">
                    Set up automated, zero-touch metadata tracking for a new
                    or ongoing model run on PPAN. Never write a Data
                    Management Plan manually again.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        start_tracking_button_clicked = st.button(
            "Start Tracking",
            key="button_start_tracking",
            type="primary",
            disabled=disabled,
            use_container_width=True,
        )
        if start_tracking_button_clicked:
            st.session_state.selected_template = "TRACKER"
            st.rerun()

    with column_two:
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 12px; padding: 20px; margin-bottom: 20px;
                height: 220px; transition: transform 0.2s ease;">
                <h4 style="margin-top: 0; color: #1e3a8a; display: flex;
                    align-items: center; gap: 8px;">
                    Retroactive Form Automation (The Typer)
                </h4>
                <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;
                    margin-bottom: 0;">
                    Already have your data and PDFs? Upload them here to have
                    AI instantly generate your compliance forms.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        automate_forms_button_clicked = st.button(
            "Automate Existing Forms",
            key="button_automate_forms",
            type="primary",
            disabled=disabled,
            use_container_width=True,
        )
        if automate_forms_button_clicked:
            st.session_state.selected_template = "README"
            st.rerun()

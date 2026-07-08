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
                (READMEs, NOAA Data Management Plans) directly from
                publications and source files.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Key Capabilities")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 12px; padding: 20px; margin-bottom: 20px;
                min-height: 180px; transition: transform 0.2s ease;">
                <h4 style="margin-top: 0; color: #1e3a8a; display: flex;
                    align-items: center; gap: 8px;">
                    Document Generator
                </h4>
                <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;
                    margin-bottom: 0;">
                    Upload dataset files, scientific papers, or metadata dumps
                    to generate standard formats. Edit answers on the fly,
                    review missing information, and export files as Word
                    (.docx) or Markdown (.md).
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 12px; padding: 20px; margin-bottom: 20px;
                min-height: 180px; transition: transform 0.2s ease;">
                <h4 style="margin-top: 0; color: #1e3a8a; display: flex;
                    align-items: center; gap: 8px;">
                    LLM Judge Evaluation
                </h4>
                <p style="color: #475569; font-size: 0.9rem; line-height: 1.5;
                    margin-bottom: 0;">
                    Audit and score historical extraction runs. Run
                    multi-iteration stability tests to compute item-level
                    agreement scores (Gwet's AC1) and verify accuracy against
                    the source documents.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Workflow Overview")
    st.markdown(
        """
        1. **Select a template** from the sidebar navigation
           (e.g. README or Data Management Plan).
        2. **Upload reference files** (scientific text files, publications,
           netCDF headers) and trigger AI generation.
        3. **Review and edit** the generated fields directly in the tabbed
           interface to fill in missing details.
        4. **Download** your final curated document in Markdown or Word.
        5. **Audit the run** in the LLM Judge tab to inspect agreement
           scores and ensure output stability.
        """
    )

    st.markdown(
        "<div style='margin-top: 2rem; margin-bottom: 1rem;'>",
        unsafe_allow_html=True,
    )
    if st.button("Start Generating Documentation", type="primary", disabled=disabled):
        st.session_state.selected_template = "README"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

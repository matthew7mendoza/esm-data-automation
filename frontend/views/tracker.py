"""
Tracker onboarding view for initiating new experiments.
"""


import streamlit as st

__all__ = ["render_tracker_view"]


def render_tracker_view(*, disabled: bool) -> None:
    """
    Renders the day zero onboarding hub for new experiments.
    """
    back_button_clicked = st.button("Back to Overview", key="tracker_back_button")
    if back_button_clicked:
        # We must import OVERVIEW_PAGE here, but since it's just a string,
        # we can use "OVERVIEW"
        st.session_state.selected_template = "OVERVIEW"
        st.rerun()

    st.title("Day Zero Onboarding Hub")
    st.markdown(
        """
        Welcome to the Metadata Tracker setup.
        Select your model archetype below to generate your initial
        `project_summary.yaml` payload and retrieve the CLI execution
        commands for your supercomputer environment.
        """
    )

    selected_model_archetype = st.selectbox(
        "Select Model Archetype",
        options=["GFDL SPEAR", "GFDL CM4", "GFDL ESM4", "GFDL SHiELD"],
        disabled=disabled,
        key="tracker_model_archetype_selectbox",
    )

    experiment_name = st.text_input(
        "Experiment Name",
        placeholder="e.g. spear_run_01",
        disabled=disabled,
        key="tracker_experiment_name_input",
    )

    generate_button_clicked = st.button(
        "Generate Setup Command",
        type="primary",
        disabled=disabled,
        key="tracker_generate_button",
    )
    if generate_button_clicked:
        if not experiment_name:
            st.error("Please provide an Experiment Name.")
            return

        st.success("Setup instructions generated successfully.")

        st.markdown("### Next Steps (Run on PPAN)")
        st.markdown(
            "SSH into your supercomputer and run the following commands "
            "in your work directory:"
        )

        installation_command = "pip install esm-tracker"
        execution_command = (
            f'esm-tracker init --experiment="{experiment_name}" '
            f'--model="{selected_model_archetype}"'
        )

        st.code(f"{installation_command}\n{execution_command}", language="bash")

        st.markdown(
            """
            Once `esm-tracker` finishes scanning your NetCDF files, it will
            generate a `project_summary.yaml` file. You can then take that file
            and drop it into the **Retroactive Form Automation (The Typer)**
            tool from the Overview page to instantly generate your Data
            Management Plan.
            """
        )

"""
Tracker onboarding view for initiating new experiments.
"""

import streamlit as st

from frontend.client import generate_api_token

__all__ = ["render_tracker_view"]


def _build_cli_instructions(
    package_manager_selection: str,
    experiment_name: str,
    selected_model_archetypes: list[str],
    api_token: str,
) -> tuple[str, str]:
    if package_manager_selection == "conda":
        installation_command = "conda install -c matthew7mendoza esm-tracker"
    else:
        installation_command = "pip install esm-tracker"

    model_string: str = ", ".join(selected_model_archetypes)
    execution_command = (
        f'esm-tracker init --experiment="{experiment_name}" '
        f'--model="{model_string}" --token="{api_token}"'
    )
    return installation_command, execution_command


def _handle_generation_button_click(
    experiment_name: str,
    selected_model_archetypes: list[str],
    package_manager_selection: str,
) -> None:
    """Processes the form submission, generates tokens, and renders output."""
    if not experiment_name:
        st.error("Please provide an Experiment Name.")
        return

    if not selected_model_archetypes:
        st.error("Please select at least one Model Archetype.")
        return

    if "tracker_api_token" not in st.session_state:
        with st.spinner("Generating secure API token..."):
            st.session_state.tracker_api_token = generate_api_token()

    api_token: str | None = st.session_state.tracker_api_token

    if not api_token:
        st.error(
            "Failed to generate an API token. "
            "Please ensure the backend is running."
        )
        return

    st.success("Setup instructions and secure token generated successfully.")
    st.markdown("### Next Steps (Run in Terminal)")
    st.markdown(
        "Open your terminal and run the following commands "
        "in your work directory:"
    )

    installation_command, execution_command = _build_cli_instructions(
        package_manager_selection, experiment_name, selected_model_archetypes, api_token
    )

    st.code(f"{installation_command}\n{execution_command}", language="bash")
    st.markdown(
        """
        Once `esm-tracker` finishes scanning your NetCDF files, it will
        generate a `project_summary.yaml` file. You can then take that file
        and drop it into the **Process Existing Manual Documents**
        tool from the Overview page to synthesize your Data
        Management Plan.
        """
    )


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

    st.title("Automated Tracker Initialization")
    st.markdown(
        """
        Configure your model archetype below to generate the execution
        commands and secure API token required for metadata extraction
        within your compute environment.
        """
    )

    selected_model_archetypes = st.multiselect(
        "Select Model Archetype(s)",
        options=["GFDL SPEAR", "GFDL CM4", "GFDL ESM4", "GFDL SHiELD"],
        default=["GFDL SPEAR"],
        disabled=disabled,
        key="tracker_model_archetypes_multiselect",
    )

    package_manager_selection = st.radio(
        "Preferred Package Manager",
        options=["conda", "pip"],
        horizontal=True,
        disabled=disabled,
        key="tracker_package_manager_radio",
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
        _handle_generation_button_click(
            experiment_name=experiment_name,
            selected_model_archetypes=selected_model_archetypes,
            package_manager_selection=package_manager_selection,
        )

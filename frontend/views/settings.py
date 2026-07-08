"""Streamlit layout rendering interface configurations and environment overrides."""
from typing import Final, cast

import requests
import streamlit as st

from frontend.client import create_custom_template, extract_template_questions
from frontend.protocols import ConfigState
from frontend.ui_constants import BACKEND_URL

__all__: Final[list[str]] = ["render_settings_view"]

SETTINGS_API_URL: Final[str] = f"{BACKEND_URL}/api/settings"
RESET_API_URL: Final[str] = f"{BACKEND_URL}/api/settings/reset"

def _fetch_active_settings() -> ConfigState | None:
    """Pulls existing state from backend over isolated REST call."""
    try:
        response = requests.get(SETTINGS_API_URL, timeout=5)
    except requests.exceptions.RequestException:
        st.error("Failed to fetch settings from backend system.")
        return None

    if response.status_code != 200:
        return None

    return cast(ConfigState, response.json())

def _commit_runtime_update(
    payload: dict[str, str | float | dict[str, str]] | ConfigState, /
) -> bool:
    """Pushes new memory block to configuration agent."""
    try:
        response = requests.patch(
            SETTINGS_API_URL, json=cast(dict[str, str | float], payload), timeout=5
        )
    except requests.exceptions.RequestException:
        return False

    return response.status_code == 200

def _initialize_local_state() -> None:
    """Guards session state to ensure single network trip."""
    fetched = _fetch_active_settings()
    if not fetched:
        st.warning(
            "Systems offline: Verification parameters isolated from backend API."
        )
        return
    st.session_state.local_config_state = fetched

def _recognize_provider(api_key: str) -> str:
    """Detects provider from common API key prefixes."""
    api_key = api_key.strip()
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("sk-proj-") or api_key.startswith("sk-"):
        return "openai"
    if api_key.startswith("nvapi-"):
        return "nemotron"
    return ""

def _on_custom_key_added() -> None:
    key = st.session_state.get("temp_api_key", "").strip()
    name = st.session_state.get("temp_api_name", "").strip()
    provider = _recognize_provider(key)
    if key and name and provider:
        payload = st.session_state.local_config_state.copy()
        payload["api_key_input"] = key
        payload["custom_key_name"] = name
        payload["recognized_provider"] = provider
        _commit_runtime_update(payload)

        st.session_state.local_config_state = _fetch_active_settings()
        st.session_state.temp_api_key = ""
        st.session_state.temp_api_name = ""
        st.toast(f"Successfully ingested {name}!")

def _render_form_fields(  # noqa: C901
    state: ConfigState
) -> tuple[str, float, str, str, str, str, str]:
    """Render setting fields and returns the UI values"""
    st.markdown("### Active Execution Target")
    if "temp_api_key" not in st.session_state:
        st.session_state.temp_api_key = ""
    if "temp_api_name" not in st.session_state:
        st.session_state.temp_api_name = ""

    st.text_input(
        "API Provider Secret Key",
        type="password",
        key="temp_api_key",
    )

    api_key = st.session_state.temp_api_key
    recognized_provider = _recognize_provider(api_key) if api_key else ""

    if recognized_provider:
        st.success(f"Recognized provider: {recognized_provider.title()}")
        st.text_input(
            "Name this key (Press Enter to ingest)",
            key="temp_api_name",
            on_change=_on_custom_key_added
        )

    engine_choices: list[str] = ["gemini", "nemotron"]
    custom_providers = state.get("custom_key_providers") or {}
    for custom_provider in custom_providers:
        if custom_provider not in engine_choices:
            engine_choices.append(custom_provider)

    current_engine = str(state.get("global_chosen_engine", "gemini"))
    if current_engine not in engine_choices:
        current_engine = "gemini"

    col1, col2 = st.columns([0.9, 0.1])
    with col1:
        chosen_engine = st.selectbox(
            "Select Active Engine",
            options=engine_choices,
            index=engine_choices.index(current_engine),
            format_func=lambda engine_name: (
                f"{engine_name.upper()} (Configured Model)"
                if engine_name == "gemini"
                else (
                    engine_name.title()
                    if engine_name not in ["gemini", "nemotron"]
                    else engine_name.upper()
                )
            ),
        )
    with col2:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        is_custom = chosen_engine not in ["gemini", "nemotron"]
        if is_custom and st.button("Remove", key=f"del_{chosen_engine}"):
            payload = state.copy()
            custom_providers_from_payload = cast(dict[str, object], payload).get("custom_key_providers")  # noqa: E501
            if not isinstance(custom_providers_from_payload, dict):
                custom_providers_from_payload = {}
            custom_dict = dict[str, str](custom_providers_from_payload)
            custom_dict.pop(chosen_engine, None)
            payload["custom_key_providers"] = custom_dict
            if payload.get("global_chosen_engine") == chosen_engine:
                payload["global_chosen_engine"] = "gemini"
            if _commit_runtime_update(payload):
                st.session_state.local_config_state = _fetch_active_settings()
                st.toast(f"Removed custom engine {chosen_engine}")
                st.rerun()


    temperature = st.slider(
        "LLM Generation Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(state.get("llm_temperature", 0.0)),
        step=0.05,
    )

    generator_prompt = st.text_area(
        "Generator System Core Prompt",
        value=str(state.get("generator_system_prompt", "")),
        height=150,
    )

    judge_prompt = st.text_area(
        "LLM Judge Evaluation Core Prompt",
        value=str(state.get("judge_system_prompt", "")),
        height=150,
    )

    return (
        "",
        temperature,
        generator_prompt,
        judge_prompt,
        str(chosen_engine),
        "",
        ""
    )

def _handle_save_action(
    state: ConfigState,
    api_key: str,
    temp: float,
    gen_prompt: str,
    judge_prompt: str,
    chosen_engine: str,
    custom_name: str,
    recognized_provider: str,
) -> None:
    """Helper to process the save settings action."""
    payload: dict[str, str | float | dict[str, str]] = {
        "llm_temperature": temp,
        "api_key_input": api_key,
        "generator_system_prompt": gen_prompt,
        "judge_system_prompt": judge_prompt,
        "database_endpoint": str(state.get("database_endpoint", "")),
        "global_chosen_engine": chosen_engine,
        "custom_key_name": custom_name,
        "recognized_provider": recognized_provider,
    }

    if _commit_runtime_update(payload):
        st.session_state.local_config_state = payload
        st.session_state.global_chosen_engine = chosen_engine
        st.toast("Configurations successfully saved!")
        st.rerun()
    else:
        st.error("Server synchronization rejected config schema")

def _render_action_buttons(  # noqa: C901
    state: ConfigState,
    api_key: str,
    temp: float,
    gen_prompt: str,
    judge_prompt: str,
    chosen_engine: str,
    custom_name: str,
    recognized_provider: str,
) -> None:
    """Render Save/Reset buttons and handle their actions."""
    st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)

    unsaved_changes = False

    if unsaved_changes:
        st.info(
            " Reminder: Don't forget to click 'Save Settings' "
            "to save your changes!"
        )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Save Settings", type="primary", use_container_width=True):
            _handle_save_action(
                state,
                api_key,
                temp,
                gen_prompt,
                judge_prompt,
                chosen_engine,
                custom_name,
                recognized_provider,
            )

    with col2:
        if st.button(
            "Reset Default Settings", type="secondary", use_container_width=True
        ):
            try:
                response = requests.post(RESET_API_URL, timeout=5)
            except requests.exceptions.RequestException:
                st.error("Failed to execute state transition")
                return
            if response.status_code != 200:
                st.error("Server rejected factory reset request.")
                return

            del st.session_state.local_config_state
            st.toast("Factory settings successfully restored!")
            st.rerun()

def render_settings_view() -> None:
    """Renders the UI elements"""
    st.header("System Settings")

    if "local_config_state" not in st.session_state:
        _initialize_local_state()

    if "local_config_state" not in st.session_state:
        return

    state = st.session_state.local_config_state

    (
        api_key,
        temp,
        gen_prompt,
        judge_prompt,
        chosen_engine,
        custom_name,
        recognized_provider,
    ) = _render_form_fields(state)

    _render_custom_templates_section()

    _render_action_buttons(
        state=state,
        api_key=api_key,
        temp=temp,
        gen_prompt=gen_prompt,
        judge_prompt=judge_prompt,
        chosen_engine=chosen_engine,
        custom_name=custom_name,
        recognized_provider=recognized_provider,
    )

def _render_custom_templates_section() -> None:  # noqa: C901
    st.markdown("---")
    st.header("Custom Form Templates")
    st.markdown(
        "Upload a document containing the questions you want to extract "
        "and save as a custom template."
    )

    template_name = st.text_input(
        "Template Name (e.g. DMP, MY_FORM)", key="custom_template_name_input"
    )
    template_desc = st.text_input(
        "Description (optional)", key="custom_template_desc_input"
    )
    uploaded_file = st.file_uploader(
        "Upload template document",
        type=["txt", "md", "pdf", "docx"],
        key="custom_template_file"
    )

    btn_disabled = not uploaded_file or not template_name.strip()
    if (
        st.button("Analyze & Extract Questions", type="primary", disabled=btn_disabled)
        and uploaded_file
        and template_name.strip()
    ):
        with st.spinner("Extracting questions..."):
                file_bytes = uploaded_file.read()
                questions = extract_template_questions(file_bytes, uploaded_file.name)
                if questions:
                    st.session_state.pending_custom_template_questions = questions
                    st.session_state.pending_custom_template_name = (
                        template_name.strip()
                    )
                    st.session_state.pending_custom_template_desc = (
                        template_desc.strip()
                    )
                    st.rerun()
                else:
                    st.error("Failed to extract questions from the document.")

    if "pending_custom_template_questions" in st.session_state:
        st.markdown("### Review & Edit Questions")
        questions = st.session_state.pending_custom_template_questions

        with st.form("custom_template_form"):
            updated_questions = []
            for index, question in enumerate(questions):
                updated_question = st.text_area(
                    f"Question {index+1}", value=question, key=f"custom_q_{index}"
                )
                if updated_question.strip():
                    updated_questions.append(updated_question.strip())

            new_qs = st.text_area(
                "Add new questions (one per line, optional)",
                key="custom_q_new"
            )

            if st.form_submit_button("Save Custom Template"):
                for line in new_qs.split('\n'):
                    if line.strip():
                        updated_questions.append(line.strip())

                name = st.session_state.pending_custom_template_name
                desc = st.session_state.pending_custom_template_desc
                if create_custom_template(name, updated_questions, desc):
                    st.success(f"Template '{name}' saved successfully!")
                    del st.session_state.pending_custom_template_questions
                    del st.session_state.pending_custom_template_name
                    del st.session_state.pending_custom_template_desc
                    st.rerun()
                else:
                    st.error("Failed to save template. It might already exist.")

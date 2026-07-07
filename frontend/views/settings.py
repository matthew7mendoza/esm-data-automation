"""Streamlit layout rendering interface configurations and environment overrides."""
from typing import Final, cast

import requests
import streamlit as st

from frontend.protocols import ConfigState
from frontend.ui_constants import BACKEND_URL

__all__: Final[list[str]] = ["render_settings_view"]

SETTINGS_API_URL: Final[str] = f"{BACKEND_URL}/api/settings"
RESET_API_URL: Final[str] = f"{BACKEND_URL}/api/settings/reset"

def _fetch_active_settings() -> dict[str, object] | None:
    """Pulls existing state from backend over isolated REST call."""
    try:
        res = requests.get(SETTINGS_API_URL, timeout=5)
    except requests.exceptions.RequestException:
        st.error("Failed to fetch settings from backend system.")
        return None

    if res.status_code != 200:
        return None

    return cast(dict[str, object], res.json())

def _commit_runtime_update(payload: dict[str, str | float], /) -> bool:
    """Pushes new memory block to configuration agent."""
    try:
        res = requests.patch(SETTINGS_API_URL, json=payload, timeout=5)
    except requests.exceptions.RequestException:
        return False

    return res.status_code == 200

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

def _render_form_fields(
    state: ConfigState
) -> tuple[str, float, str, str, str, str, str]:
    """Render setting fields and returns the UI values"""
    st.markdown("### Active Execution Target")

    api_key = st.text_input(
        "API Provider Secret Key",
        value=str(state.get("api_key_input", "")),
        type="password",
    )

    recognized_provider = _recognize_provider(api_key) if api_key else ""
    custom_name = str(state.get("custom_key_name", ""))

    if recognized_provider:
        st.success(f"Recognized provider: {recognized_provider.title()}")
        custom_name = st.text_input("Name this key", value=custom_name)
    else:
        custom_name = ""

    engine_choices: list[str] = ["gemini", "nemotron"]
    if custom_name and custom_name not in engine_choices:
        engine_choices.append(custom_name)

    current_engine = str(state.get("global_chosen_engine", "gemini"))
    if current_engine not in engine_choices:
        current_engine = "gemini"

    chosen_engine = st.selectbox(
        "Select Active Engine",
        options=engine_choices,
        index=engine_choices.index(current_engine),
        format_func=lambda x: (
            f"{x.upper()} (Configured Model)"
            if x == "gemini"
            else x.title() if x not in ["gemini", "nemotron"] else x.upper()
        ),
    )


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
        api_key,
        temperature,
        generator_prompt,
        judge_prompt,
        str(chosen_engine),
        custom_name,
        recognized_provider
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
    payload: dict[str, str | float] = {
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

def _render_action_buttons(
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
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Commit Node Settings", type="primary", use_container_width=True):
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
            "Reset Factory Defaults", type="secondary", use_container_width=True
        ):
            try:
                res = requests.post(RESET_API_URL, timeout=5)
            except requests.exceptions.RequestException:
                st.error("Failed to execute state transition")
                return
            if res.status_code != 200:
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

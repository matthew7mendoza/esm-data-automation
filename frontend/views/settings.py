from typing import Final

import requests
import streamlit as st

from frontend.config import BACKEND_URL

__all__ = ["render_settings_view"]

SETTINGS_API_URL: Final[str] = f"{BACKEND_URL}/api/settings"
METRICS_API_URL: Final[str] = f"{BACKEND_URL}/api/metrics/tokens"

def _fetch_active_settings() -> dict[str, object] | None:
    try:
        response = requests.get(SETTINGS_API_URL, timeout=5)
        if response.status_code != 200:
            return None
        return response.json()
    except requests.exceptions.RequestException:
        st.error("Could not pull settings frame from server boundary.")
        return None

def _fetch_token_telemetry() -> int:
    try:
        response = requests.get(METRICS_API_URL, timeout=5)
        if response.status_code != 200:
            return 0
        return response.json().get("total_tokens_consumed", 0)
    except requests.exceptions.RequestException:
        return 0

def render_settings_view() -> None:
    st.header("System Settings & Telemetry")
    current_config = _fetch_active_settings()
    if not current_config:
        st.warning("Failed to map connection configurations to backend API.")
        return

    tokens_used = _fetch_token_telemetry()
    st.markdown("### Core System Telemetry")
    st.metric(label="Token usage", value=f"{tokens_used:,} tokens")
    st.divider()

    st.markdown("### Hyperparameters & Context Overrides")
    api_key = st.text_input(
        "API Provider Secret Key",
        value=str(current_config.get("api_key_input", "")),
        type="password",
        help="Input authentication tokens for external LLM execution providers cleanly."
    )

    temperature = st.slider(
        "LLM Generation Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(current_config.get("llm_temperature", 0.2)),
        step=0.05,
        help="Lower numbers -> strict values. Higher -> variation. 0 recommended."
    )

    db_endpoint = st.text_input(
        "Database Engine Endpoint URI String",
        value=str(current_config.get("database_endpoint", "")),
        help="Active targets for the application's storage models connection string."
    )

    generator_prompt = st.text_area(
        "Generator System Core Prompt",
        value=str(current_config.get("generator_system_prompt", "")),
        rows=5
    )

    judge_prompt = st.text_area(
        "LLM Judge Evaluation Core Prompt",
        value=str(current_config.get("judge_system_prompt", "")),
        rows=5
    )

    if st.button("Save System Configuration", type="primary", use_container_width=True):
        updated_payload = {
            "llm_temperature": temperature,
            "api_key_input": api_key,
            "generator_system_prompt": generator_prompt,
            "judge_system_prompt": judge_prompt,
            "database_endpoint": db_endpoint
        }
        try:
            res = requests.patch(SETTINGS_API_URL, json=updated_payload, timeout=5)
            if res.status_code == 200:
                st.toast("Configurations successfully saved back to storage layers!")
            else:
                st.error("Server rejected the serialization matrix structure updates.")
        except requests.exceptions.RequestException as error_fault:
            st.error(f"Network exception intercepted: {error_fault}")

"""
Standalone page layer rendering operational controls and hardware metrics.
"""

from typing import Any, Final, cast

import requests
import streamlit as st

from backend.esm_data.models import TokenUsageMetricsResponse
from frontend.config import BACKEND_URL

__all__ = ["render_settings_view"]

SETTINGS_API_URL: Final[str] = f"{BACKEND_URL}/api/settings"
RESET_API_URL: Final[str] = f"{BACKEND_URL}/api/settings/reset"
METRICS_API_URL: Final[str] = f"{BACKEND_URL}/api/metrics/tokens"


def _fetch_active_settings() -> dict[str, object] | None:
    """Queries backend interface for existing operational parameters."""
    try:
        res = requests.get(SETTINGS_API_URL, timeout=5)
    except requests.exceptions.RequestException:
        st.error("Could not pull settings frame from server boundary.")
        return None

    if res.status_code != 200:
        return None

    return cast(dict[str, object], res.json())


def _fetch_token_telemetry() -> int:
    """Extracts total processed runtime tokens from telemetry logs."""
    try:
        res = requests.get(METRICS_API_URL, timeout=5)
    except requests.exceptions.RequestException:
        return 0

    if res.status_code != 200:
        return 0

    try:
        token_metrics = TokenUsageMetricsResponse.model_validate(res.json())
        return token_metrics.total_tokens_consumed
    except Exception:
        return 0


def render_settings_view() -> None:
    """Renders the settings and metric dashboard controls in isolation."""
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
        help="Input credentials for external execution providers cleanly.",
    )

    raw_temp = current_config.get("llm_temperature", 0.2)
    val_temp = float(raw_temp) if isinstance(raw_temp, (int, float)) else 0.2

    temperature = st.slider(
        "LLM Generation Temperature",
        min_value=0.0,
        max_value=1.0,
        value=val_temp,
        step=0.05,
        help="Lower -> deterministic; higher -> variation. Temp 0 recommended.",
    )

    db_endpoint = st.text_input(
        "Database Engine Endpoint URI String",
        value=str(current_config.get("database_endpoint", "")),
        help="Active targets for the storage engine connection string.",
    )

    generator_prompt = st.text_area(
        "Generator System Core Prompt",
        value=str(current_config.get("generator_system_prompt", "")),
        height=150,
    )

    judge_prompt = st.text_area(
        "LLM Judge Evaluation Core Prompt",
        value=str(current_config.get("judge_system_prompt", "")),
        height=150,
    )

    st.divider()
    _render_action_buttons(
        temperature, api_key, generator_prompt, judge_prompt, db_endpoint
    )


def _render_action_buttons(
    temp: float, key: str, gen: str, judge: str, db: str
) -> None:
    """Handles layout form post submissions cleanly with zero logic nesting."""
    col_save, col_reset = st.columns(2)

    with col_save:
        _handle_save_action(temp, key, gen, judge, db)

    with col_reset:
        _handle_reset_action()


def _handle_save_action(
    temp: float, key: str, gen: str, judge: str, db: str
) -> None:
    """Processes save events directly using flat guard returns."""
    if not st.button(
        "Save System Configuration", type="primary", use_container_width=True
    ):
        return

    payload: dict[str, Any] = {
        "llm_temperature": temp,
        "api_key_input": key,
        "generator_system_prompt": gen,
        "judge_system_prompt": judge,
        "database_endpoint": db,
    }

    try:
        res = requests.patch(SETTINGS_API_URL, json=payload, timeout=5)
    except requests.exceptions.RequestException as err:
        st.error(f"Network exception intercepted: {err}")
        return

    if res.status_code != 200:
        st.error("Server rejected the serialization structure.")
        return

    st.toast("Configurations successfully saved!")
    st.rerun()


def _handle_reset_action() -> None:
    """Processes factory rollback requests directly using flat guard returns."""
    if not st.button(
        "Reset to Factory Defaults", type="secondary", use_container_width=True
    ):
        return

    try:
        res = requests.post(RESET_API_URL, timeout=5)
    except requests.exceptions.RequestException as err:
        st.error(f"Network transport boundary failure: {err}")
        return

    if res.status_code != 200:
        st.error("Failed to execute baseline state transitions.")
        return

    st.toast("Factory settings successfully restored!")
    st.rerun()

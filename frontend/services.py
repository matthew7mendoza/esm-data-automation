"""Streamlit orchestration logic for generation and auditing."""

import time
from typing import cast

import requests
import streamlit as st

from frontend.client import get_task_profile
from frontend.protocols import TaskProfileDict, UploadedFileProtocol
from frontend.ui_constants import BACKEND_URL, MODEL_CONFIGURATIONS
from shared.models import TaskId

__all__ = ["send_audit_request", "send_generation_request"]


def _surface_backend_warnings(*, network_payload: dict[str, object] | None) -> None:
    """Looks for backend warnings and puts them to the frontend."""
    if not network_payload:
        return
    warning_messages = network_payload.get("warnings")
    if not isinstance(warning_messages, list):
        return
    for specific_warning in warning_messages:
        st.warning(f"Warning notice: {specific_warning}")


def _save_completed_generation(
    task_profile: TaskProfileDict, returned_task_identifier: str
) -> None:
    st.session_state.generator_report = task_profile.get("report")
    st.session_state.source_context = task_profile.get("source_context")
    st.session_state.current_task_id = returned_task_identifier
    st.session_state.current_task_custom_name = task_profile.get("custom_name")

    if "history_selectbox" in st.session_state:
        st.session_state.history_selectbox = "-- Select Past Run --"


def _poll_generation_task(
    validated_task_identifier: TaskId,
    returned_task_identifier: str,
    status_container: object,
) -> bool:
    """Polls the task until it succeeds, fails, or times out."""
    delta_generator_container = cast(
        st.delta_generator.DeltaGenerator, status_container
    )
    for _ in range(450):
        delta_generator_container.info(
            "AI is analyzing file and compiling documentation... Please wait..."
        )
        task_profile = get_task_profile(task_identifier=validated_task_identifier)
        if not task_profile:
            delta_generator_container.empty()
            st.error("Lost communication tracking link with backend processing!")
            return False

        _surface_backend_warnings(network_payload=cast(dict[str, object], task_profile))

        current_status = task_profile.get("status")
        if current_status == "FAILED":
            delta_generator_container.empty()
            st.error(f"Processing routine crashed: {task_profile.get('detail')}")
            return False

        if current_status != "COMPLETED":
            time.sleep(2)
            continue

        _save_completed_generation(task_profile, returned_task_identifier)
        delta_generator_container.empty()
        st.success("Answers successfully written!")
        return True

    delta_generator_container.empty()
    st.error("Task timed out.")
    return False


def send_generation_request(  # noqa: C901
    *,
    target_document: str,
    chosen_engine: str,
    uploaded_files: list[UploadedFileProtocol],
    custom_name: str = "",
) -> None:
    """Assembles operational file buffers and sends processing request."""
    st.session_state.audit_metrics = None

    files_payload = [
        ("files", (upload_file.name, upload_file.getvalue(), upload_file.type))
        for upload_file in uploaded_files
    ]

    request_payload = {
        "target_doc": target_document,
        "model_provider": MODEL_CONFIGURATIONS.get(chosen_engine, chosen_engine),
        "custom_name": custom_name,
    }

    try:
        generation_response = requests.post(
            f"{BACKEND_URL}/api/generate",
            data=request_payload,
            files=files_payload,
            timeout=60,
        )
    except requests.exceptions.ConnectionError as connection_failure:
        st.error(f"Failed to connect to backend layer. {connection_failure}")
        return
    except requests.exceptions.Timeout as timeout_failure:
        st.error(f"Backend connection timed out. {timeout_failure}")
        return
    except requests.exceptions.RequestException as generic_network_failure:
        st.error(f"General network error to backend. {generic_network_failure}")
        return

    if generation_response.status_code not in (200, 202):
        failure_details = generation_response.json().get("detail")
        st.error(f"Backend processing failure: {failure_details}")
        return

    returned_task_identifier = generation_response.json().get("task_id", "")
    if not returned_task_identifier:
        st.error("Invalid task response from processing node.")
        return

    validated_task_identifier = TaskId(returned_task_identifier)
    status_container = st.empty()
    _poll_generation_task(
        validated_task_identifier, returned_task_identifier, status_container
    )


def send_audit_request(
    *,
    chosen_engine: str,
    answers: dict[str, str],
    judge_iterations: int,
    source_context: str,
) -> dict[str, object] | None:
    """Sends generated answers to an AI judge to evaluate consistency."""
    audit_payload: dict[str, str | int | dict[str, str]] = {
        "source_context": source_context,
        "answers": answers,
        "iterations": judge_iterations,
    }

    query_parameters = {
        "model_provider": MODEL_CONFIGURATIONS.get(chosen_engine, chosen_engine)
    }

    try:
        audit_response = requests.post(
            f"{BACKEND_URL}/api/audit",
            json=audit_payload,
            params=query_parameters,
            timeout=120,
        )
    except requests.exceptions.ConnectionError as connection_failure:
        st.error(f"Failed to connect to audit server. {connection_failure}")
        return None
    except requests.exceptions.Timeout as timeout_failure:
        st.error(f"Audit server connection timed out. {timeout_failure}")
        return None
    except requests.exceptions.RequestException as generic_network_failure:
        st.error(f"General network error to audit server. {generic_network_failure}")
        return None

    if audit_response.status_code != 200:
        audit_failure_details = audit_response.json().get("detail")
        st.error(f"Audit server error: {audit_failure_details}")
        return None

    audit_metrics_payload = cast(dict[str, object], audit_response.json())
    st.session_state.audit_metrics = audit_metrics_payload

    _surface_backend_warnings(network_payload=audit_metrics_payload)

    st.success("Audit complete!")

    audit_metadata = cast(dict[str, object], audit_metrics_payload.get("metadata", {}))
    gwet_agreement_score = cast(float, audit_metadata.get("global_gwets_ac1", 0.0))

    st.metric("Agreement score (Gwet's AC1)", gwet_agreement_score)
    item_stability_metrics = audit_metrics_payload.get(
        "item_level_stability_metrics", []
    )
    st.dataframe(item_stability_metrics, width="stretch")
    return audit_metrics_payload

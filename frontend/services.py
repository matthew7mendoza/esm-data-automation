"""
Streamlit orchestation 
"""

import time
from typing import Any, cast

import requests
import streamlit as st

from backend.esm_data.models import TaskId
from frontend.api import get_task_profile
from frontend.config import BACKEND_URL, MODEL_CONFIGURATIONS
from frontend.protocols import UploadedFileProtocol

__all__ = ["send_generation_request", "send_audit_request"]

def send_generation_request(
    *,
    target_document: str,
    chosen_engine: str,
    uploaded_files: list[UploadedFileProtocol],
    custom_name: str = "",
) -> None:
    """
    Assembles operational file buffers and polls back
    """

    st.session_state.audit_metrics = None

    file_payload = [
        ("files", (file.name, file.getvalue(), file.type)) for file in uploaded_files
    ]

    data_payload = {
        "target_doc": target_document,
        "model_provider": MODEL_CONFIGURATIONS[chosen_engine],
        "custom_name": custom_name,
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/generate",
            data=data_payload,
            files=file_payload,
            timeout=60,
        )
    except requests.exceptions.RequestException as network_error:
        st.error(f"Could not reach background API layer... Error: {network_error}")
        return
    
    if response.status_code not in (200, 202):
        st.error(f"Backend processing failure: {response.json().get('detail')}")
        return
    
    raw_task_id = response.json().get("task_id", "")
    if not raw_task_id:
        st.error("Invalid task response from processing node.")
        return
    
    task_id = TaskId(raw_task_id)
    status_container = st.empty()

    for _ in range(450):
        status_container.info("AI is analyzing file and compiling documentation... Please wait...")
        task_profile = get_task_profile(task_id=task_id)

        if not task_profile:
            status_container.empty()
            st.error("Lost communication tracking link with backend processing!")
            return
        
        status = task_profile.get("status")

        if status == "FAILED":
            status_container.empty()
            st.error(f"Processing routine crashed: {task_profile.get('detail')}")
            return
        
        if status != "COMPLETED":
            time.sleep(2)
            continue

        st.session_state.generator_report = task_profile.get("report")
        st.session_state.source_context = task_profile.get("source_context")

        if "history_selectbox" in st.session_state:
            st.session_state.history_selectbox = "-- Select Past Run --"

        status_container.empty()
        st.success("Answers successfully written!")
        return
    
def send_audit_request(
    *,
    chosen_engine: str,
    answers: dict[str, str],
    judge_iterations: int,
    source_context: str
) -> dict[str, Any] | None:
    """
    Sends the generated answers to an AI judge to evaluate how consistent they are
    """

    audit_payload = {
        "source_context": source_context,
        "answers": answers,
        "iterations": judge_iterations,
    }

    parameters = {
        "model_provider": MODEL_CONFIGURATIONS[chosen_engine]
    }

    try:
        audit_response = requests.post(
            f"{BACKEND_URL}/api/audit",
            json=cast(Any, audit_payload),
            params=parameters,
            timeout=120
        )
    except requests.exceptions.RequestException as network_error:
        st.error(f"Communication loss with audit server: {network_error}")
        return None
    
    if audit_response.status_code != 200:
        st.error(f"Audit server error: {audit_response.json().get('detail')}")
        return None
    
    metrics = cast(dict[str, Any], audit_response.json())
    st.session_state.audit_metrics = metrics

    st.success("Audit complete!")

    metadata = metrics.get("metadata", {})
    kappa_score = metadata.get("global_gwets_ac1", 0.0)

    st.metric("Agreement score (Gwet's AC1)", kappa_score)
    st.dataframe(metrics.get("item_level_stability_metrics", []), width="stretch")
    return metrics

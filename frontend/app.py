"""
Streamlit front end
takes files and gives to backend
"""

import contextlib
import logging
import time
from typing import Protocol, TypedDict, Final

import requests
import streamlit as st

from backend.esm_data.models import ExtractionReport, TaskId

__all__ = ["main"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL: Final[str] = "http://localhost:8000"

MODEL_CONFIGURATIONS: Final[dict[str, str]] = {  
    "Gemini": "gemini",
    "Nvidia": "nemotron"
}

class TaskProfileDict(TypedDict):
    task_id: str
    status: str
    custom_name: str | None
    report: ExtractionReport | None
    source_context: str | None
    detail: str | None

class UploadedFileProtocol(Protocol):
    name: str
    type: str
    def getvalue(self) -> bytes: ...

def fetch_server_templates() -> list[str]:
    """
    Asks backend for list of available document forms to fill
    """
    try:
        response = requests.get(f"{BACKEND_URL}/api/templates", timeout=5)
    except requests.exceptions.RequestException as error:
        logger.warning(f"Unable to fetch templates from worker program: {error}")
        return ["DMP", "README"]

    if response.status_code != 200:
        logger.warning(f"Backend returned unexpected status: {response.status_code}")
        return ["DMP", "README"]

    return response.json()

def _get_task_profile(task_id: TaskId) -> TaskProfileDict | None:
    """
    helper function Gets backend training tickets
    """
    
    with contextlib.suppress(requests.exceptions.RequestException):
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)

        if response.status_code != 200:
            return None
        
        return response.json()
    
    return None

def send_generation_request(
    *,
    target_document: str,
    chosen_engine: str,
    uploaded_files: list[UploadedFileProtocol],
    custom_name: str = ""
) -> None:
    """
    Packs up the loaded files and sends them to the backend to be processed
    """

    file_payload = [
        ("files", (file.name, file.getvalue(), file.type))
        for file in uploaded_files
    ]

    data_payload = {
        "target_doc": target_document,
        "model_provider": MODEL_CONFIGURATIONS[chosen_engine],
        "custom_name": custom_name
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/generate",
            data=data_payload,
            files=file_payload,
            timeout=60
        )
    except requests.exceptions.RequestException as network_error:
        st.error(f"Could not reach background API layer... Is uvicorn running? Error: {network_error}")
        return
    
    if response.status_code not in (200, 202):
        st.error(f"Backend processing failure: {response.json().get('detail')}")
        return
    
    task_id = response.json().get("task_id")
    status_container = st.empty()

    for _ in range(450):
        status_container.info("AI is analyzing files and compiling compliance documentation... Please wait...")

        if not (task_profile := _get_task_profile(task_id)):
            status_container.empty()
            st.error("Lost communication tracking link with backend processing node.")
            return
        
        match task_profile.get("status"):
            case "COMPLETED":
                st.session_state.generator_report = task_profile.get("report")
                st.session_state.source_context = task_profile.get("source_context")
                if "history_selectbox" in st.session_state:
                    st.session_state.history_selectbox = "-- Select Past Run --"
                status_container.empty()
                st.success("Answers successfully written!")
                return
            
            case "FAILED":
                status_container.empty()
                st.error(f"Processing routine crashed: {task_profile.get('detail')}")
                return
            
            case _:
                time.sleep(2)

    status_container.empty()
    st.error("operational job teacking timed out!")


def send_audit_request(
    *,
    chosen_engine: str,
    answers: dict[str, str],
    judge_iterations: int
) -> None:
    """
    Sends the current answers back to the background 
    worker program to run accuracy test, then displays final scores on the screen
    """

    audit_payload = {
        "source_context": st.session_state.source_context,
        "answers": answers,
        "iterations": judge_iterations
    }

    parameters = {"model_provider": MODEL_CONFIGURATIONS[chosen_engine]}

    try:
        audit_response = requests.post(
            f"{BACKEND_URL}/api/audit",
            json=audit_payload,
            params=parameters,
            timeout=120
        )
    except requests.exceptions.RequestException as network_error:
        st.error(f"Communication loss with audit server: {network_error}")
        return
    
    
    if audit_response.status_code != 200:
        st.error(f"Audit server error: {audit_response.json().get('detail')}")
        return
    
    metrics = audit_response.json()
    st.success("Audit complete!")
    kappa_score = metrics.get("metadata", {}).get("global_gwets_ac1", 0.0)
    st.metric("Agreement score (Gwet's AC1)", kappa_score)
    st.dataframe(
        metrics.get("item_level_stability_metrics", []),
        use_container_width=True
    )


def render_answers_and_missing_sections() -> None:
    """
    Column for the answers that the AI found, one for the information the AI
    could not find
    """

    st.markdown("---")
    left_column, right_column = st.columns(2)

    with left_column:
        st.subheader("Extracted Answers")
        answers = st.session_state.generator_report.get("extracted_answers", {})
        for question, answer in answers.items():
            st.markdown(f"**{question}**\n> {answer}")

    with right_column:
        st.subheader("Missing Information")
        missing = st.session_state.generator_report.get("missing_information", [])
        if not missing:
            st.success("The AI found answers to all questions for this template!")
        for missing_question in missing:
            st.error(f"- {missing_question}")



def on_history_change() -> None:
    """
    Prevents other random clicks on the page from cluttering historical view.
    Uses strict early-exit guard rails to keep execution depth perfectly flat.
    """

    selected_job_name = st.session_state.history_selectbox
    if not selected_job_name or selected_job_name == "-- Select Past Run --":
        return
    
    if not (chosen_job := st.session_state.get("task_mapping", {}).get(selected_job_name)):
        return

    if not (task_id := chosen_job.get("task_id")):
        return
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
    except requests.exceptions.RequestException as network_transport_fault:
        logger.error("Network communication loss when trying to read historical entries", exc_info=True)
        st.error(f"Network error trying to fetch historical file profile: {network_transport_fault}")
        return
    
    if response.status_code != 200:
        st.error("Failed to extract full analysis data from backend node.")
        return
    
    full_job_payload = response.json()
    st.session_state.generator_report = full_job_payload.get("report")
    st.session_state.source_context = full_job_payload.get("source_context")

def render_historical_sidebar() -> None:
    """
    Ask backend for past runs, then renders
    """

    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
    except requests.exceptions.RequestException as connection_offline_error:
        logger.warning(f"Unable to read connection tracking indexes: {connection_offline_error}")
        st.sidebar.caption("History tracker offline!")
        return
    
    if response.status_code != 200:
        st.sidebar.caption("History tracker offline!")
        return
    
    past_tasks = response.json()
    completed_tasks = [
        task for task in past_tasks if task.get("status") == "COMPLETED"
    ]

    if not completed_tasks:
        st.sidebar.caption("No history")
        return
    
    task_options = {
        (f"{task.get('custom_name')} ({task['task_id'][:8]})" if task.get("custom_name")
        else f"Job {task['task_id'][:8]}"): task
        for task in completed_tasks
    }

    st.session_state.task_mapping = task_options
    options_list = ["-- Select Past Run --", *task_options]

    st.sidebar.selectbox(
        "Reload a past analysis:",
        options=options_list,
        key="history_selectbox",
        on_change=on_history_change,
        disabled=st.session_state.job_running
    )


def main() -> None:
    """
    Main Control Flow Pipeline
    """

    st.set_page_config(page_title="ESM Data Automation", layout="wide")
    st.title("ESM Data Automation")
    st.markdown("Automatically answer templates w/ uploaded info + check for accuracy using AI")

    if "generator_report" not in st.session_state:
        st.session_state.generator_report = None
    if "source_context" not in st.session_state:
        st.session_state.source_context = None
    if "job_running" not in st.session_state:
        st.session_state.job_running = False
    
    if st.session_state.job_running and "pending_generation" in st.session_state:
        args = st.session_state.pop("pending_generation")
        send_generation_request(
            target_document=args["target_document"],
            chosen_engine=args["chosen_engine"],
            uploaded_files=args["uploaded_files"],
            custom_name=args["custom_name"]
        )
        st.session_state.job_running = False
        st.rerun()

    if st.session_state.job_running and "pending_audit" in st.session_state:
        args = st.session_state.pop("pending_audit")
        current_answers = st.session_state.generator_report.get("extracted_answers", {})
        send_audit_request(
            chosen_engine=args["chosen_engine"],
            answers=current_answers,
            judge_iterations=args["judge_iterations"]
        )
        st.session_state.job_running = False
        st.rerun()

    render_historical_sidebar()
    
    st.sidebar.header("Settings")
    
    chosen_engine = st.sidebar.selectbox(
        "Select AI Model",
        list(MODEL_CONFIGURATIONS.keys()),
        disabled=st.session_state.job_running
    )
    target_document = st.sidebar.selectbox(
        "Chose a form template to fill out",
        fetch_server_templates(),
        disabled=st.session_state.job_running
    )
    judge_iterations = st.sidebar.slider(
        "How many times should the judge test?",
        2, 10, 3,
        disabled=st.session_state.job_running
    )

    st.header(f"1. Generate {target_document}")
    uploaded_files = st.file_uploader(
        "Drop you scientific data, READMEs, publications, ect... here:",
        accept_multiple_files=True,
        disabled=st.session_state.job_running
    )

    custom_name = st.text_input(
        "Label this extraction run (optional):", 
        placeholder="ReadME Spear project #1",
        disabled=st.session_state.job_running
    )

    # Clicking this button now simply captures parameters and restarts the flow
    if st.button(
        "Read Files & Write Answers",
        type="primary",
        disabled=not uploaded_files or st.session_state.job_running
    ):
        st.session_state.job_running = True
        st.session_state.pending_generation = {
            "target_document": target_document,
            "chosen_engine": chosen_engine,
            "uploaded_files": uploaded_files,
            "custom_name": custom_name
        }
        st.rerun()

    if not st.session_state.generator_report:
        return
    
    render_answers_and_missing_sections()

    st.markdown("---")
    st.header("2. LLM Judge")
    st.markdown("Run the judge test to quantify the accuracy of {taget_document}")

    if st.button(
        "Run Stability Test",
        disabled=st.session_state.job_running
    ):
        st.session_state.job_running = True
        st.session_state.pending_audit = {
            "chosen_engine": chosen_engine,
            "judge_iterations": judge_iterations
        }
        st.rerun()


if __name__ == "__main__":
    main()




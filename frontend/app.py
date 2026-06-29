"""
Streamlit front end
takes files and gives to backend
"""

import logging
import streamlit as st
import requests
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:8000"

MODEL_CONFIGURATIONS = {
    "Gemini": "gemini",
    "Nvidia": "Nemotron"
}

def fetch_server_templates() -> list[str]:
    """
    Asks backend for list of available document forms to fill
    """

    try:
        response = requests.get(f"{BACKEND_URL}/api/templates", timeout=5)
        if response.status_code == 200:
            return response.json()
        
    except requests.exceptions.RequestException as error:
        logger.warning(f"Unable to fetch templates from worker program: {error}")

    # Must fix this hard coding later

    return ["DMP", "README"]


def _get_task_profile(task_id: str) -> dict | None:
    """
    helper function Gets backend training tickets
    """
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException:
        pass
    return None

def send_generation_request(
    target_document: str,
    chosen_engine: str,
    uploaded_files: list
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
        "model_provider": MODEL_CONFIGURATIONS[chosen_engine]
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

        task_profile = _get_task_profile(task_id)
        if not task_profile:
            status_container.empty()
            st.error("Lost communication tracking link with backend processing ndoe.")
            return
        
        match task_profile.get("status"):
            case "COMPLETED":
                st.session_state.generator_report = task_profile.get("report")
                st.session_state.source_context = task_profile.get("source_context")
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
    chosen_engine: str,
    answers: dict,
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

        if audit_response.status_code == 200:
            metrics = audit_response.json()
            st.success("Audit complete!")
            kappa_score = metrics.get("metadata", {}).get("global_gwets_ac1", 0.0)
            st.metric("Agreement score (Gwet's AC1)", kappa_score)
            st.dataframe(
                metrics.get("item_level_stability_metrics", []),
                use_container_width=True
            )
        else:
            st.error(
                f"Audit server error: {audit_response.json().get('detail')}"
            )
        
    except requests.exceptions.RequestException as network_error:
        st.error(f"Communication loss with audit server: {network_error}")


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


def render_historical_sidebar():
    """
    Asks backend for past runs,
    then renders
    """

    st.sidebar.markdown("---")
    st.sidebar.header("Job History Log")

    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=5)
        if response.status_code == 200:
            past_tasks = response.json()

            completed_tasks = [task for task in past_tasks if task.get("status") == "COMPLETED"]

            if not completed_tasks:
                st.sidebar.caption("No history jobs")
                return
            
            task_options = {f"Job {task['task_id'][:8]} ({task['task_id'][:8]})": task for task in completed_tasks}
            selected_job_name = st.sidebar.selectbox("Reload a past analysis:", ["-- Select Past Run --"] + list(task_options.keys()))

            if selected_job_name != "-- Select Past Run --":
                chosen_job = task_options[selected_job_name]
                st.session_state.generator_report = chosen_job.get("report")
                st.session_state.source_context = chosen_job.get("source_context")
                st.sidebar.success("Loaded data from historical record!")
    
    except Exception as error:
        st.sidebar.caption("History tracker offline.")

def main() -> None:
    """
    Main
    """

    st.set_page_config(page_title="ESM Data Automation", layout="wide")
    st.title("ESM Data Automation")
    st.markdown("Automatically answer templates w/ uploaded info + check for accuracy using AI")

    if "generator_report" not in st.session_state:
        st.session_state.generator_report = None
    if "source_context" not in st.session_state:
        st.session_state.source_context = None
    
    st.sidebar.header("Settings")
    chosen_engine = st.sidebar.selectbox("Select AI Mode", list(MODEL_CONFIGURATIONS.keys()))
    target_document = st.sidebar.selectbox("Chose a form template to fill out", fetch_server_templates())
    judge_iterations = st.sidebar.slider("How many times should the judge test?", 2, 10, 3)

    st.header(f"1. Generate {target_document}")
    uploaded_files = st.file_uploader(
        "Drop you scientific data, READMEs, publications, ect... here:",
        accept_multiple_files=True
    )

    if st.button("Read Files & Write Answers", type="primary", disabled=not uploaded_files):
        with st.spinner("Processing files..."):
            send_generation_request(target_document, chosen_engine, uploaded_files)

    if not st.session_state.generator_report:
        return
    
    render_answers_and_missing_sections()
    render_historical_sidebar()

    st.markdown("---")
    st.header("2. LLM Judge")
    st.markdown("Run the judge test to quantify the accurate of {target_documnet}")

    if st.button("Run Stability Test"):
        with st.spinner(f"Request {judge_iterations} concurrent background audit passes..."):
            current_answers = st.session_state.generator_report.get("extracted_answers", {})
            send_audit_request(chosen_engine, current_answers, judge_iterations)

if __name__ == "__main__":
    main()
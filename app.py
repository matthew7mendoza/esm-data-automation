"""
Main streamlit dashboard

Allows you to upload files, tells AI to read them and fill out forms
runs tests to see if the AI's answered are stable and trustworthy
"""

import os
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
import yaml
from dotenv import load_dotenv

from src.providers import get_provider, LLMProvider
from src.generator import DocumentGenerator
from src.judge import LLMJudge
from src.document import extract_text, EXTRACTOR_MAP
from src.models import SpearAutomationError, CorruptedDocumentError, AgentConfigurationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

MODEL_CONFIGURATIONS = {
    "Gemini": {
        "name": "gemini"
    },
    "GPT-4o": {
        "name": "openai",
        "model_name": "gpt-4o"
    },
    "Nvidia Nemotron": {
        "name": "openai",
        "model_name": "blank for now",
        "base_url": "blank for now"
    }
}

def get_available_templates() -> list[str]:
    """
    Look inside src/templates.yaml to see which forms can be filled out
    """

    template_path = Path("src/templates.yaml")
    if not template_path.exists():
        return["DMP", "README"]
    
    with open(template_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
        return list(data.get("DOCUMENT_TEMPLATES", {}).keys())   
       


def handle_document_generation(
    provider: LLMProvider,
    uploaded_files: list,
    target_doc: str
) -> tuple[dict[str, Any], str] | tuple[None, None]:
    """
    Takes the uploaded files, saves into temporary folder.
    Extracts text,
    returns AI report & giant string containing all file text
    """

    with tempfile.TemporaryDirectory() as temp_directory:
        temp_path = Path(temp_directory)

        for uploaded_file in uploaded_files:
            (temp_path / uploaded_file.name).write_bytes(
                uploaded_file.getbuffer()
            )

        try:
            generator = DocumentGenerator(provider=provider)
            report = generator.generate_draft_from_directory(target_doc, temp_path)

            source_blocks = [
                f"--- SOURCE CONTEXT ASSET: {file.name} ---\n{extract_text(file)}"
                for file in temp_path.iterdir()
                if file.suffix.lower() in EXTRACTOR_MAP
            ]
            combined_text = "\n\n".join(source_blocks)

            return report, combined_text
        
        except CorruptedDocumentError as error:
            st.error(f"Could not read one of the files because it was broken: {error}")
        except SpearAutomationError as error:
            st.error(f"The AI had trouble building the document: {error}")
        except Exception as error:
            st.error(f"Something unexpected happened: {error}")

        return None, None
    
def render_extracted_answers(answers: dict[str, str]) -> None:
    """
    Takes a dictionary of questions and answers and displays them
    """
    st.subheader("Extracted Answers")
    if not answers:
        st.info("The AI could not find any clear answers for this template in your documents.")
        return
    
    for question, answer in answers.items():
        st.markdown(f"**{question}**\n> {answer}")


def render_missing_information(missing: list[str]) -> None:
    """
    Takes a list of questions that the AI could not answer and prints them
    """

    st.subheader("Missing information")
    if not missing:
        st.success("The Ai fonud answers to all questions on this template.")
        return

    for missing_question in missing:
        st.error(f"- {missing_question}")



def execute_stability_audit(
    provider: LLMProvider, 
    source_context: str,
    answers: dict[str, Any],
    iterations: int
) -> dict[str, Any] | None:
    """
    Runs the background testing and catches errors
    """

    answers_as_text = json.dumps(answers, indent=2)

    try:
        judge = LLMJudge(provider=provider)
        return asyncio.run(judge.run_stability_stress_test_async(
            source_content=source_context,
            paste_content=answers_as_text,
            prefix_label="APP_EVAL",
            i_iterations=iterations
        ))
    
    except AgentConfigurationError as config_error:
        st.error(f"Config error: templates.yaml instructions file is missing or broken: {config_error}")

    except ValueError as value_error:
        st.error(f"Authentication error: The Ai client did not start correctly: {value_error}")

    except Exception as unexpected_error:
        logger.error("An unknown failure happened during stabiltiy audit", exc_info=True)
        st.error(f"System Error: audit failed due to unexpected problem: {unexpected_error}")

    return None


def handle_quality_audit(provider: LLMProvider, source_context: str, answers: dict[str, Any], iterations: int) -> None:
    """
    Create new section for LLM Judge
    When this button is clicked it will make the AI grade the answers
    """

    st.markdown("---")
    st.header("2. LLM Judge")
    st.markdown("Run the judge test to make sure the answers match your original uploaded files")

    if not st.button("Run Stability Test"):
        return
    
    with st.spinner(f"Running {iterations} tests..."):
        metrics = execute_stability_audit(provider, source_context, answers, iterations)

    if not metrics:
        return
    
    st.success("Audit complete")

    kappa_score = metrics.get("metadata", {}).get("global_fleiss_kappa", 0.0)
    st.metric("Agreement score", kappa_score)

    st.subheader("Question by question breakdown")
    st.dataframe(metrics.get("item_level_stability_metrics", []), use_container_width=True)


def main() -> None:
    """
    Manages page flow
    """

    st.set_page_config(page_title="ESM Data Automation", layout="wide")
    st.title("ESM Data Automation")
    st.markdown("Autotmatically answer templates w/ uploaded info + check for accuracy using AI")

    if "generator_report" not in st.session_state:
        st.session_state.generator_report = None
    if "source_context" not in st.session_state:
        st.session_state.source_context = None
    
    st.sidebar.header("Settings")
    chosen_engine = st.sidebar.selectbox("Select AI Model", list(MODEL_CONFIGURATIONS.keys()))
    target_document = st.sidebar.selectbox("Chose a form template to fill out", get_available_templates())
    judge_iterations = st.sidebar.slider("How many times should the judge test?", 2, 10, 3)

    try:
        config = MODEL_CONFIGURATIONS[chosen_engine].copy()
        active_provider = get_provider(**config)
    except Exception as env_error:
        st.error(f"Error: Unable to load provider LLM Api key")
        return

    st.header(f"1. Generate {target_document}")
    uploaded_files = st.file_uploader(
        "Drop your scientific data, descriptions, papers, ect.. here:",
        accept_multiple_files=True,
        type=[ext.replace(".", "") for ext in EXTRACTOR_MAP.keys()]
    ) 

    if st.button("Read Files & Write Answers", type="primary", disabled=not uploaded_files):
        with st.spinner("Reading your files and asking the AI to process them..."):
            report, context = handle_document_generation(active_provider, uploaded_files, target_document)
            if report and context:
                st.session_state.generator_report = report
                st.session_state.source_context = context
                st.success("Answers saved")
            
    if st.session_state.generator_report:
        st.markdown("---")

        left_column, right_column = st.columns(2)

        with left_column:
            render_extracted_answers(
                st.session_state.generator_report.get("extracted_answers", {})
            )
    
        with right_column:
            render_missing_information(
                st.session_state.generator_report.get("missing_information", [])
            )
    
        handle_quality_audit(
            provider=active_provider,
            source_context=st.session_state.source_context,
            answers=st.session_state.generator_report.get("extracted_answers", {}),
            iterations=judge_iterations
        )

if __name__ == "__main__":
    main()
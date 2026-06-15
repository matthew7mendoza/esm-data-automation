import os
import logging
from pathlib import Path

from src.document_reader import extract_text, EXTRACTOR_MAP
from src.ai_agent import LLM_Agent
from src.exceptions import DocumentExtractionError, AgentExecutionError

logger = logging.getLogger(__name__)

def generate_document_draft(
    target_document_type: str,
    input_dir: Path | str,
    api_key: str
) -> None:
    """
    Handles reading of input files and calls AI agent to generate a draft.
    """

    input_path = Path(input_dir)

    agent = LLM_Agent(api_key=api_key, temperature=0.0)
    print("\nAI AGENT ACTIVATED")

    if not input_path.exists():
        input_path.mkdir(parents=True)
        print(f"Created '{input_path.resolve()}'. Please drop your files in the folder and re-run.")
        return
    
    supporting_documents = [
        file for file in input_path.iterdir()
        if file.is_file() and file.suffix.lower() in EXTRACTOR_MAP
    ]

    if not supporting_documents:
        print(f"No supporting files found in '{input_path.resolve()}'")
        return
    
    print(f"Configuration loaded. Found {len(supporting_documents)} supported file(s):")
    for document in supporting_documents:
        print(f" -> {document.name}")

    print(f"\n--- Assembling knowledge base for {target_document_type} ---")
    combined_document_text = ""

    for path in supporting_documents:
        try:
            print(f"Reading: {path.name}...")
            extracted = extract_text(path)
            combined_document_text += f"\n\n--- SOURCE: {path.name} ---\n{extracted}"
        except FileNotFoundError:
            print(f"Could not locate file at {path}")
        except DocumentExtractionError as read_err:
            print(f"Failed to extract text: {read_err}")

    if not combined_document_text.strip():
        print("\nNo text could be extracted from the provided files.")
        return
    
    print(f"\n ---Processing {target_document_type} extraction via LLM--- ")
    try:
        result = agent.process_document(target_document_type, combined_document_text)
        print("Extraction complete.\n")

        print(f"---- GENERATED {target_document_type} DRAFT ----\n")
        for question, answer in result.get("extracted_answers", {}).items():
            print(f"{question}\n> {answer}\n")
        
        missing_info = result.get("missing_information", [])
        if missing_info:
            print("----- MISSING INFORMATION -----")
            print("The AI could not find answers to these questions in your documents:\n")
            for missing in missing_info:
                print(f"- {missing}")
    
    except AgentExecutionError as agent_err:
        print(f"\nThe AI Agent encountered an error: {agent_err}")

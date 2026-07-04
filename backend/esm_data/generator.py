"""
Prompts, parameters, AI lifecycle processing
Reads from template.json at startupt
Uses AI to answer questions
"""

from importlib.resources import files
import logging
from pathlib import Path
from typing import TypedDict

import openai
import yaml

from backend.esm_data.document import EXTRACTOR_MAP, extract_text
from backend.esm_data.models import (
    AgentConfigurationError,
    AgentExecutionError,
    CorruptedDocumentError,
    DocumentExtractionError,
    ExtractionReport,
    FormResponses,
)
from backend.esm_data.providers import LLMProvider

__all__ = ["TemplateConfig", "DocumentGenerator"]
logger = logging.getLogger(__name__)

class TemplateConfig(TypedDict):
    questions: list[str]
    description: str | None

class DocumentGenerator:
    """
    AI model read documents and puts specific answers into the questions
    """

    __slots__ = ("provider", "instructions", "templates")

    instructions: str
    templates: dict[str, TemplateConfig]

    def __init__(self, provider: LLMProvider) -> None:
        if not provider:
            raise ValueError("An active LLM provider must be present!")
        self.provider = provider
        self.instructions, self.templates = self._load_configuration_blueprints()

    def __repr__(self) -> str:
        """technical output string"""
        return f"DocumentGenerator(provider={self.provider})"

    def __str__(self) -> str:
        """readable representation string"""
        return f"Document Generator Module [Bound to Engine: {self.provider.__class__.__name__}]"

    def _load_configuration_blueprints(self) -> tuple[str, dict[str, TemplateConfig]]:
        """
        Loads the system prompts and document questions from local templates.yaml
        """
        ###ALERT
        ### ALERT
        ### UPDATE PATH WHEN YOU EVENTUALLY CHANGE THE NAMRE
        config_path = Path(str(files("backend.esm_data"))) / "templates.yaml"
        if not config_path.exists():
            raise AgentConfigurationError(f"The templates.yaml file is missing at: {config_path.resolve()}")
        
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
            return data["DEFAULT_LLM_INSTRUCTIONS"], data["DOCUMENT_TEMPLATES"]
        except (OSError, yaml.YAMLError) as document_read_fault:
            raise AgentConfigurationError("Unable to read / parse templates.yaml file. Check that format is correct.") from document_read_fault
    
    def execute_extraction(self, target_questions: list[str], content_payload: str) -> ExtractionReport:
        """
        Sends the document text and list of questions to AI,
        forcing AI to return strict JSON response
        """

        formatted_questions = "\n".join(f"- {question}" for question in target_questions)
        user_prompt = f"QUESTIONS TO ANSWER: \n{formatted_questions}\n\nSOURCE DOCUMENT:\n{content_payload}"

        try:
            validated_data: FormResponses = self.provider.generate_structured(
                prompt=user_prompt,
                system_instruction=self.instructions,
                response_schema=FormResponses
            )
        except (openai.OpenAIError, ValueError, TypeError, RuntimeError) as api_communication_fault:
            logger.error("Failed to communicate with AI API backend model engines!", exc_info=True)
            raise AgentExecutionError("Could not get a response from the AI model API") from api_communication_fault
        
        flat_answers = {item.question: item.answer for item in validated_data.extracted_answers}
        return {
            "extracted_answers": flat_answers,
            "missing_information": validated_data.missing_information
        }
    
    def generate_draft_from_directory(self, target_document_type: str, input_dir: Path | str) -> ExtractionReport:
        """
        Finds all supported files in a folder, extracts their text, combines them together, sends to the AI
        """

        if not (active_template := self.templates.get(target_document_type.upper())):
            raise ValueError(f"The document type '{target_document_type} was not found in templates.yaml'")
        
        input_path = Path(input_dir)
        if not input_path.exists():
            input_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Folder was missing, so a new empty folder was created: {input_path.resolve()}")
            return {"extracted_answers": {}, "missing_information": []}
        
        valid_workspace_files = [
            file for file in input_path.iterdir()
            if file.is_file() and file.suffix.lower() in EXTRACTOR_MAP
        ]

        if not valid_workspace_files:
            raise AgentExecutionError("Finished checking the folder, no text could successfully be read from any of the files")

        aggregated_text_blocks = []
        for file_path in valid_workspace_files:
            try:
                text_block = extract_text(file_path)
                aggregated_text_blocks.append(f"--- SOURCE CONTENT ASSET: {file_path.name} ---\n{text_block}")
            except (DocumentExtractionError, CorruptedDocumentError) as read_failure:
                logger.error(f"Skipping file {file_path.name} because it could not be read: {read_failure}")

        if not aggregated_text_blocks:
            raise AgentExecutionError("Finished checking the folder, no text could be successfully read from any of the files")

        final_unified_context = "\n\n".join(aggregated_text_blocks)

        return self.execute_extraction(
            target_questions=active_template["questions"],
            content_payload=final_unified_context
        )




import logging
from typing import Any
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.config import DOCUMENT_TEMPLATES, FormResponses, DEFAULT_LLM_INSTRUCTIONS
from src.exceptions import AgentConfigurationError, AgentExecutionError

logger = logging.getLogger(__name__)

class LLM_Agent:
    def __init__(
      self,
      api_key: str,
      model_name: str = "gemini-3.1-pro-preview",
      temperature: float = 0.0,
      system_instructions: str = DEFAULT_LLM_INSTRUCTIONS      
    ):
        if not api_key:
            raise AgentConfigurationError("A valid API key must be provided.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.system_instructions = system_instructions
        
    def extract_data(self, questions_list, document_text, schema):
        """
        Feeds the text to the model and forces the output into the provided format schema.
        Transforms API's strict JSON list back into a usable Python dictionary
        """
        
        formatted_questions = "\n".join(f"- {q}" for q in questions_list)
        prompt = f"QUESTIONS TO ANSWER:\n{formatted_questions}\n\nSOURCE DOCUMENT:\n{document_text}"

        config = types.GenerateContentConfig(
            system_instruction = self.system_instructions,
            temperature = self.temperature,
            response_mime_type = "application/json",
            response_schema = schema,
        )

        try:
            response = self.client.models.generate_content(
                model = self.model_name,
                contents = prompt,
                config = config
            )
        except Exception as api_err:
            logger.error(f"LLM API call failed: {api_err}")
            raise AgentExecutionError("Failed to communicate with LLM API") from api_err

        if not response.text:
            raise AgentExecutionError("Empty response from LLM API.")
        
        try:
            if not response.parsed:
                raise AgentExecutionError("The AI returned an empty response.")
            
            validated_data = response.parsed

        except ValidationError as val_err:
            logger.error(f"LLM output violated schema format: {val_err}")
            raise AgentExecutionError("The AI returned improperly formatted JSON.") from val_err
        
        flat_answers = {item.question: item.answer for item in validated_data.extracted_answers}

        return {
            "extracted_answers": flat_answers,
            "missing_information": validated_data.missing_information
        }


    def process_document(self, doc_type: str, document_text: str) -> dict[str, Any]:
        doc_type_upper = doc_type.upper()
        config = DOCUMENT_TEMPLATES.get(doc_type_upper)

        if not config:
            raise ValueError(f"Unsupported document type: '{doc_type}'. Available types {list(DOCUMENT_TEMPLATES.keys())}")
        
        return self.extract_data(
            questions_list = config["questions"],
            document_text = document_text,
            schema = config["schema"]
        )
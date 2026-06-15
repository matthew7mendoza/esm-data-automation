from pydantic import BaseModel, Field


DEFAULT_LLM_INSTRUCTIONS = (
    "You are a strict data management assistant. Your objective is to extract information "
    "from user-provided scientific documents and metadata to accurately answer form questions "
    "for Data Management Plans, ReadMes, and DOIs. "
    "Keep answers concise and strictly technical. If the provided document does not contain "
    "the answer to a requested question, DO NOT guess. Instead, add that exact question to the "
    "missing_information list."
)


class AnswerPair(BaseModel):
    question: str = Field(description="The exact form question.")
    answer: str = Field(description="The extracted answer.")

class FormResponses(BaseModel):
    extracted_answers: list[AnswerPair] = Field(
        description="List mapping the exact form question to the extracted answer."
    )

    missing_information: list[str] = Field(
        description="List of exact questions from the prompt that could not be answered using the text."
    )

DOCUMENT_TEMPLATES = {
    "DMP": {

        "questions": [
           "1. What opportunity is from UCLA?\n",
           "2. What is the deadline for the STARS program?\n",
           "3. How many students participate in the Capital One opportunity?"
        ],
        "schema": FormResponses
    },
}
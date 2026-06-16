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

#ENTER THE FORMAT OF THE DMP TEMPLATE HERE.
DOCUMENT_TEMPLATES = {
    "DMP": {
        "questions": [
            "1. General Description of Data",
            "1.1 Name of Data/Project:",
            "1.2 Project purpose & summary:",
            "1.3 Timeframe (One-time or ongoing):",
            "1.4 Temporal coverage:",
            "1.5 Geographic coverage:",
            "1.7 Type(s) of data:",
            "1.8 Approximate data volume:",
            "1.9 Data collection method(s):",
            "2 & 3. Contacts & Responsible Party",
            "Point of Contact (Name, Title, Affiliation, Email):",
            "Responsible Party (Name, Title, Email):",
            "4. Resources",
            "Have resources for management been identified?:",
            "5. Data Lineage and Quality",
            "5.1 Processing workflow:",
            "5.2 Quality control procedures:",
            "6. Data Documentation",
            "6.1 Does metadata comply with requirements?:",
            "6.3 URL of metadata folder or data catalog (DOI):",
            "7. Data Access",
            "7.2 Intended data access method(s):",
            "7.3 Name of facility providing access",
            "7.4 Tentative dissemination date:",
            "8. Data Preservation",
            "8.1 Long term data archive location:",
            "8.4 Data protection and backup plan:"
        ],
        "schema": FormResponses
    },
}
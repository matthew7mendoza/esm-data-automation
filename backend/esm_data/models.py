"""
This file defines the standard data structures, rules, and custom errors
"""

from typing import Literal, NewType, TypedDict

from pydantic import BaseModel, ConfigDict, Field

# namespace
__all__ = [
    "AgentConfigurationError",
    "AgentExecutionError",
    "AnswerPair",
    "AuditRequest",
    "ComplianceCategoryGroup",
    "ComplianceScoringSchema",
    "CorruptedDocumentError",
    "DocumentExtractionError",
    "ExtractionReport",
    "FormResponses",
    "MasterAuditPayloadSchema",
    "NoveltyEntrySchema",
    "RubricItemConfig",
    "SpearAutomationError",
    "SystemSettingsPayload",
    "TaskRenameRequest",
    "TaskReportUpdateRequest",
    "TaskStatusResponse",
    "TemplateCreateRequest",
    "TokenUsageMetricsResponse",
]


class SystemSettingsPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    llm_temperature: float = Field(0.2, ge=0.0, le=1.0)
    api_key_input: str = Field("")
    generator_system_prompt: str = Field(...)
    judge_system_prompt: str = Field(...)
    database_endpoint: str = Field(...)


class TokenUsageMetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_tokens_consumed: int = Field(0, ge=0)


TaskId = NewType("TaskId", str)
ItemId = NewType("ItemId", str)
TemplateName = NewType("TemplateName", str)


# ----------Error Boundaries----------------
class SpearAutomationError(Exception):
    """
    Base exception for all errors within SPEAR automation project.
    """

    pass


class DocumentExtractionError(SpearAutomationError):
    """
    Base exception for all document extraction failures.
    """

    pass


class CorruptedDocumentError(DocumentExtractionError):
    """
    Raised when the file exists but MarkItDown fails to read data
    """

    pass


class AgentConfigurationError(SpearAutomationError):
    """
    Raised when the agent lacks required credentials or configuration.
    """

    pass


class AgentExecutionError(SpearAutomationError):
    """
    Raised when the LLM fails to generate or return valid data.
    """

    pass


# ---------Pydantic Schemas-----------
class RubricItemConfig(BaseModel):
    """
    Defines and validates the setup rules for a single test question
    for the LLM Judge
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        ...,
        description=(
            "The unique identifier for the question "
            "(for example, '1.1', or '2.A')."
        ),
    )
    question: str = Field(
        ..., description="The question text that the AI needs to check for accuracy."
    )
    strategy: Literal["Numeric", "Quote", "Assertion"] = Field(
        ...,
        description=(
            "The method the AI should use to look for the answer "
            "(looking for a number, a direct quote, or a general fact)."
        ),
    )


class NoveltyEntrySchema(BaseModel):
    """
    Stores the quality scores for how unqiue and useful the
    AI-generated statement is.
    """

    model_config = ConfigDict(frozen=True)

    relevance: Literal[0, 1] = Field(
        ...,
        description=(
            "Indicates if the statement is relevant (1) or not (0). "
            "If this is 0, all the other sub-scores must be 0."
        ),
    )
    originality: int = Field(
        ...,
        ge=0,
        le=3,
        description="The score for originality, from 0 (lowest) to 3 (highest).",
    )
    gap_addressing: int = Field(
        ...,
        ge=0,
        le=3,
        description=(
            "The score for how well it solves an unanswered problem, "
            "from 0 to 3"
        ),
    )
    non_obviousness: int = Field(
        ...,
        ge=0,
        le=3,
        description="The score for how unique or unexpected the idea is, from 0 to 3.",
    )


class ComplianceScoringSchema(BaseModel):
    """
    Tracks the AI's grading results and text explanations
    for a single question
    """

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(
        ..., description="The unique identifier for the question being checked."
    )
    question: str = Field(
        ..., description="The text of the question that was being evaluated."
    )
    justification: str = Field(
        ...,
        description=(
            "The explanation written by the AI Judge justifying its "
            "final grade."
        ),
    )
    answer: Literal["Yes", "No"] = Field(
        ..., description="The final answer, must be a strict 'Yes' or 'No'."
    )


class ComplianceCategoryGroup(BaseModel):
    """
    A collection of grouped compliance rules.
    """

    model_config = ConfigDict(frozen=True)

    category_name: str
    items: list[ComplianceScoringSchema]


class MasterAuditPayloadSchema(BaseModel):
    """
    Validation container for multiple LLM evaluation loops.
    Holds complete set of categorized test results from the AI evaluation loop (Judge)
    """

    model_config = ConfigDict(frozen=True)

    categories: list[ComplianceCategoryGroup]


class AnswerPair(BaseModel):
    """
    Maps a single form question with the answer the AI found for it
    """

    model_config = ConfigDict(frozen=True)

    question: str = Field(..., description="The exact form question.")
    answer: str = Field(
        ..., description="The answer text that was extracted from the source documents."
    )


class FormResponses(BaseModel):
    """
    Validates the final set of answers written by the AI for a template form.
    """

    model_config = ConfigDict(frozen=True)

    extracted_answers: list[AnswerPair] = Field(
        ..., description="List mapping form questions to extracted answers."
    )
    missing_information: list[str] = Field(
        ...,
        description=(
            "Questions that could not be verified or answered using the "
            "source documents."
        ),
    )


class ExtractionReport(TypedDict):
    """
    Explicit typedict for AI generator output
    """

    extracted_answers: dict[str, str]
    missing_information: list[str]


class TaskStatusResponse(BaseModel):
    """
    How the data should look when sent to frontend
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    status: str
    custom_name: str | None = None
    report: ExtractionReport | None = None
    source_context: str | None = None
    detail: str | None = None


class AuditRequest(BaseModel):
    """
    Pydantic schema handle input validation for JSON endpoints
    """

    model_config = ConfigDict(frozen=True)

    source_context: str
    answers: dict[str, str]
    iterations: int = 3


class TemplateCreateRequest(BaseModel):
    """
    Validates incoming JSON payload required to dynamically
    register a new custom form layout in the databse
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., description="The unique name of the document form (e.g., 'DOI')."
    )
    description: str | None = Field(
        None, description="Optional high-level technical description."
    )
    questions: list[str] = Field(..., description="Ordered list of questions")


class TaskReportUpdateRequest(BaseModel):
    """
    Validates incoming JSON payload to update the extraction report of an existing task.
    """

    model_config = ConfigDict(frozen=True)

    extracted_answers: dict[str, str] = Field(
        ..., description="Map of questions to their edited answers."
    )
    missing_information: list[str] = Field(
        ..., description="List of unanswered or missing questions."
    )


class TaskRenameRequest(BaseModel):
    """
    Validates incoming JSON payload to rename a task
    """

    model_config = ConfigDict(frozen=True)

    custom_name: str = Field(..., description="The new custom name for the task.")


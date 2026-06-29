"""
This file defines the standard data structures, rules, and custom errors
"""

from typing import Literal 
from pydantic import BaseModel, Field
from typing import Any


# Error Boundaries

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

# Pydantic Schemas

class RubricItemConfig(BaseModel):
    """
    Defines and validates the setup rules for a single test question
    for the LLM Judge
    """

    id: str = Field(..., description="The unique identifier for the question (for example, '1.1', or '2.A').")
    question: str = Field(..., description="The question text that the AI needs to check for accuracy.")
    strategy: Literal["Numeric", "Quote", "Assertion"] = Field(..., description="The method the AI should use to look for the answer (looking for a number, a direct quote, or a general fact).")

class NoveltyEntrySchema(BaseModel):
    """
    Stores the quality scores for how unqiue and useful the 
    AI-generated statement is.
    """

    relevance: Literal[0, 1] = Field(
        ..., description="Indicates if the statement is relevant (1) or not (0). If this is 0, all the other sub-scores must be 0."
    )
    originality: int = Field(..., ge=0, le=3, description="The score for originality, from 0 (lowest) to 3 (highest).")
    gap_addressing: int = Field(..., ge=0, le=3, description="The score for how well it solves an unanswered problem, from 0 to 3")
    non_obviousness: int = Field(..., ge=0, le=3, description="The score for how unique or unexpected the idea is, from 0 to 3.")

class ComplianceScoringSchema(BaseModel):
    """
    Tracks the AI's grading results and text explanations 
    for a single question
    """

    item_id: str = Field(..., description="The unique identifier for the question being checked.")
    question: str = Field(..., description="The text of the question that was being evaluated.")
    justification: str = Field(..., description="The explanation written by the AI Judge justifying its final grade.")
    answer: Literal["Yes", "No"] = Field(..., description="The final answer, must be a strict 'Yes' or 'No'.")

class ComplianceCategoryGroup(BaseModel):
    """
    A collection of grouped compliance rules.
    """

    category_name: str
    items: list[ComplianceScoringSchema]

class MasterAuditPayloadSchema(BaseModel):
    """
    Validation container for multiple LLM evaluation loops.
    Holds complete set of categorized test results from the AI evaluation loop (Judge)
    """

    categories: list[ComplianceCategoryGroup]

class AnswerPair(BaseModel):
    """
    Maps a single form question with the answer the AI found for it
    """

    question: str = Field(..., description="The exact form question.")
    answer: str = Field(..., description="The answer text that was extracted from the source documents.")

class FormResponses(BaseModel):
    """
    Validates the final set of answers written by the AI for a template form.
    """

    extracted_answers: list[AnswerPair] = Field(
        ..., description="List mapping form questions to extracted answers."
    )
    missing_information: list[str] = Field(
        ..., description="Questions that could not be verified or answered using the source documents."
    )

class TaskStatusResponse(BaseModel):
    """
    How the data should look when sent to frontend
    """

    task_id: str
    status: str
    report: dict[str, Any] | None = None
    source_context: str | None = None
    detail: str | None = None

class AuditRequest(BaseModel):
    """
    Pydantic schema handle input validation for JSON endpoints
    """

    source_context: str
    answers: dict[str, Any]
    iterations: int = 3

class TemplateCreateRequest(BaseModel):
    """
    Validates incoming JSON payload required to dynamically
    register a new custom form layout in the databse
    """

    name: str = Field(..., description="The unique name of the document form (e.g., 'DOI').")
    description: str | None = Field(None, description="Optional high-level technical description.")
    questions: list[str] = Field(..., description="Ordered list of questions")


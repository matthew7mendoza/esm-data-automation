"""
Data validation schemas and structural models for document automation
"""

from typing import Literal
from pydantic import BaseModel, Field

class NoveltyEntrySchema(BaseModel):

    """
    Evaluation of a single generated research statement
    from the LLM's output
    """

    relevance: Literal[0, 1] = Field(
        ..., description="If 0, all other sub-scores must be 0."
    )
    originality: int = Field(..., ge=0, le=3, description="Score 0-3.")
    gap_addressing: int = Field(..., ge=0, le=3, description="Score 0-3.")
    non_obviousness: int = Field(..., ge=0, le=3, description="Score 0-3.")

class ComplianceScoringSchema(BaseModel):

    """"
    Audit metric tracking for the LLM
    """

    question: str = Field(..., description="The rubric compliance verification question.")
    justification: str = Field(..., description="Natural language justification trace.")
    answer: Literal["Yes", "No"] = Field(..., description="Strict binary compliance verdict.")

class ComplianceCategoryGroup(BaseModel):

    """
    A collection of grouped compliance rules.
    """

    category_name: str
    items: list[ComplianceScoringSchema]

class MasterAuditPayloadSchema(BaseModel):

    """
    Validation container for multiple LLM evaluation loops.
    """

    categories: list[ComplianceCategoryGroup]

class AnswerPair(BaseModel):

    """
    Maps an isolated configuration form question to its extracted answer string.
    """

    question: str = Field(..., description="The exact form question.")
    answer: str = Field(..., description="The extracted answer text.")

class FormResponses(BaseModel):

    """
    Validates the output generation layer or metadata documentation templates.
    """

    extracted_answers: list[AnswerPair] = Field(
        ..., description="List mapping form questions to extracted answers."
    )
    missing_information: list[str] = Field(
        ..., description="Questions that could not be verified or answered using the source documents."
    )

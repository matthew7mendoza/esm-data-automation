"""
Schemas (format) for the LLM compliance evaluaton framework.
"""

from typing import Literal
from pydantic import BaseModel, Field

class NoveltyEntrySchema(BaseModel):

    """
    Hierarchical evaluation of a single generated research statement.
    """

    relevance: Literal[0, 1] = Field(
        ..., description="Hierarchical gate. If 0, all other sub-scores must be 0."
    )
    originality: int = Field(..., ge=0, le=3, description="Score 0-3.")
    gap_addressing: int = Field(..., ge=0, le=3, description="Score 0-3.")
    non_obviousness: int = Field(..., ge=0, le=3, description="Score 0-3.")


class ComplianceScoringSchema(BaseModel):

    """
    Audit metric tracking a single rule's verdict and supporting evidence.
    """

    question: str = Field(..., description="The rubric compliance verification question.")
    justification: str = Field(..., description="Natural language justification trace.")
    answer: Literal["Yes", "No"] = Field(..., desription="Strict binary compliance verdict.")


class ComplianceCategoryGroup(BaseModel):

    """
    A collection of grouped compliance rules.
    """

    category_name: str
    items: list[ComplianceScoringSchema]

class MasterAuditPayloadSchema(BaseModel):

    """
    Validation container for multiple LLM evaluation loops
    """

    categories: list[ComplianceCategoryGroup]


    
    
"""
Defines duck type structured interfance & schemas
"""

from typing import Protocol, TypedDict

from backend.esm_data.models import ExtractionReport, TaskId

__all__ = ["TaskProfileDict", "UploadedFileProtocol"]


class TaskProfileDict(TypedDict):
    task_id: TaskId
    status: str
    custom_name: str | None
    report: ExtractionReport | None
    source_context: str | None
    detail: str | None

class UploadedFileProtocol(Protocol):
    name: str
    type: str

    def getvalue(self) -> bytes: ...

class GenerationArgsPayload(TypedDict):
    target_document: str
    chosen_engine: str
    uploaded_files: list[UploadedFileProtocol]
    custom_name: str

class AuditArgsPayload(TypedDict):
    task_id: str
    chosen_engine: str
    answers: dict[str, str]
    judge_iterations: int
    source_context: str

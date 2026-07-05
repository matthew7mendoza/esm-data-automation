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

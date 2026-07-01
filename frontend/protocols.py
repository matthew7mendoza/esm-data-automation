"""
Defines duck type structured interfance & schemas
"""

from typing import Final, Protocol, TypedDict

from backend.esm_data.models import ExtractionReport, TaskId

__all__ = ["TaskProfileDict", "UploadedFileProtocol"]

class TaskProfileDict(TypedDict):
    task_id: TaskId
    status: str
    custom_name: str | None

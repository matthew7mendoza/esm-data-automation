"""
HTTP client operations
"""

import contextlib
import logging
from typing import Final, cast

import requests

from backend.esm_data.models import TaskId
from frontend.config import BACKEND_URL, TEMPLATE_SORT_ORDER
from frontend.protocols import TaskProfileDict

__all__ = [
    "fetch_all_historical_tasks",
    "fetch_server_templates",
    "get_task_profile",
    "update_task_report",
]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def fetch_server_templates() -> list[str]:
    """
    Ask background server for complete collection of
    document templates
    """

    try:
        response = requests.get(f"{BACKEND_URL}/api/templates", timeout=5)
    except requests.exceptions.RequestException as error:
        logger.warning(f"Unable to fetch templates from worker program: {error}")
        return ["DMP", "README"]

    if response.status_code != 200:
        logger.warning(f"Backend returned unexpected status: {response.status_code}")
        return ["DMP", "README"]

    return cast(list[str], response.json())


def get_task_profile(*, task_id: TaskId) -> TaskProfileDict | None:
    """
    Helper function tracking real-time backend updates
    """

    with contextlib.suppress(requests.exceptions.RequestException):
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)

        if response.status_code == 200:
            return cast(TaskProfileDict, response.json())

    return None


def fetch_all_historical_tasks() -> list[dict[str, object]]:
    """
    Gets every historical run from backend
    """

    with contextlib.suppress(requests.exceptions.RequestException):
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=10)

        if response.status_code == 200:
            return cast(list[dict[str, object]], response.json())

    return []


def update_task_report(
    *, task_id: str, extracted_answers: dict[str, str], missing_information: list[str]
) -> bool:
    """
    Sends a PATCH request to backend to save edited answers and missing info.
    """

    payload: dict[str, dict[str, str] | list[str]] = {
        "extracted_answers": extracted_answers,
        "missing_information": missing_information,
    }
    try:
        response = requests.patch(
            f"{BACKEND_URL}/api/tasks/{task_id}/report", json=payload, timeout=5
        )
        return response.status_code == 200
    except requests.exceptions.RequestException as error:
        logger.error(f"Failed to update task report: {error}")
        return False

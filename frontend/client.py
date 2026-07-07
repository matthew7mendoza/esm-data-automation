"""HTTP client client wrappers consuming FastAPI background service boundaries."""
import contextlib
import logging
from typing import Final, cast

import requests

from backend.esm_data.models import TaskId
from frontend.protocols import TaskProfileDict
from frontend.ui_constants import BACKEND_URL, TEMPLATE_SORT_ORDER

__all__: Final[list[str]] = [
    "fetch_all_historical_tasks",
    "fetch_server_templates",
    "get_task_profile",
    "update_task_report",
]

logger: Final[logging.Logger] = logging.getLogger(__name__)

def fetch_server_templates() -> list[str]:
    """Queries background infrastructure server for sorted document layouts."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/templates", timeout=5)
        if response.status_code == 200:
            raw_templates = cast(list[str], response.json())
            sorted_templates = [t for t in TEMPLATE_SORT_ORDER if t in raw_templates]
            others = [t for t in raw_templates if t not in TEMPLATE_SORT_ORDER]
            return sorted_templates + others
    except requests.exceptions.RequestException as error:
        logger.warning(f"Network transport down: defaulting configurations. {error}")

    return ["README", "DMP"]

def get_task_profile(*, task_id: TaskId) -> TaskProfileDict | None:
    """Tracks real-time database modifications for a running tracking ticket."""
    with contextlib.suppress(requests.exceptions.RequestException):
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
        if response.status_code == 200:
            return cast(TaskProfileDict, response.json())
    return None

def fetch_all_historical_tasks() -> list[dict[str, object]]:
    """Fetches all tracking records stored within backend relational layers."""
    with contextlib.suppress(requests.exceptions.RequestException):
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=10)
        if response.status_code == 200:
            return cast(list[dict[str, object]], response.json())
    return []

def update_task_report(
    *,
    task_id: str,
    extracted_answers: dict[str, str],
    missing_information: list[str],
) -> bool:
    """Commits user manual override updates back into database storage fields."""
    payload: Final[dict[str, dict[str, str] | list[str]]] = {
        "extracted_answers": extracted_answers,
        "missing_information": missing_information,
    }

    try:
        response = requests.patch(
            f"{BACKEND_URL}/api/tasks/{task_id}/report", json=payload, timeout=5
        )
        return response.status_code == 200
    except requests.exceptions.RequestException as error:
        logger.error(f"Failed to update task report record maps: {error}")
        return False

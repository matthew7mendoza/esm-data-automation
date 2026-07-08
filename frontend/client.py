"""HTTP client client wrappers consuming FastAPI background service boundaries."""
import logging
from typing import Final, cast

import requests

from backend.esm_data.models import TaskId
from frontend.protocols import TaskProfileDict
from frontend.ui_constants import BACKEND_URL, TEMPLATE_SORT_ORDER

__all__: Final[list[str]] = [
    "create_custom_template",
    "extract_template_questions",
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
    except requests.exceptions.RequestException as error:
        logger.warning(f"Network transport down: defaulting configurations. {error}")
        return ["README", "DMP"]

    if response.status_code != 200:
        return ["README", "DMP"]

    raw_templates = cast(list[str], response.json())
    sorted_templates = [
        template
        for template in TEMPLATE_SORT_ORDER
        if template in raw_templates
    ]
    others = [
        template
        for template in raw_templates
        if template not in TEMPLATE_SORT_ORDER
    ]
    return sorted_templates + others

def get_task_profile(*, task_id: TaskId) -> TaskProfileDict | None:
    """Tracks real-time database modifications for a running tracking ticket."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_id}", timeout=5)
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    return cast(TaskProfileDict, response.json())

def fetch_all_historical_tasks() -> list[dict[str, object]]:
    """Fetches all tracking records stored within backend relational layers."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=10)
    except requests.exceptions.RequestException:
        return []

    if response.status_code != 200:
        return []

    return cast(list[dict[str, object]], response.json())

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
    except requests.exceptions.RequestException as error:
        logger.error(f"Failed to update task report record maps: {error}")
        return False

    return response.status_code == 200

def extract_template_questions(file_bytes: bytes, filename: str) -> list[str] | None:
    """Sends a template file to the backend to extract questions."""
    files = {"file": (filename, file_bytes)}

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/templates/extract", files=files, timeout=30
        )
    except requests.exceptions.RequestException as error:
        logger.error(f"Network error during template extraction: {error}")
        return None

    if response.status_code != 200:
        logger.error(f"Failed to extract questions: {response.text}")
        return None

    return cast(list[str], response.json())

def create_custom_template(
    name: str, questions: list[str], description: str = ""
) -> bool:
    """Saves a new custom form template to the backend database."""
    payload = {
        "name": name,
        "description": description,
        "questions": questions
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/templates", json=payload, timeout=10
        )
    except requests.exceptions.RequestException as error:
        logger.error(f"Network error creating template: {error}")
        return False

    if response.status_code != 201:
        logger.error(f"Failed to create template: {response.text}")
        return False

    return True

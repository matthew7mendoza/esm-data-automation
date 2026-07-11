"""HTTP client wrappers consuming FastAPI background service boundaries."""

import logging
from typing import Final, cast

import requests

from frontend.protocols import TaskProfileDict
from frontend.ui_constants import BACKEND_URL, TEMPLATE_SORT_ORDER
from shared.models import TaskId

__all__: Final[list[str]] = [
    "approve_pending_update",
    "create_custom_template",
    "extract_template_questions",
    "fetch_all_historical_tasks",
    "fetch_pending_context",
    "fetch_server_templates",
    "generate_api_token",
    "get_task_profile",
    "update_task_report",
]

logger: Final[logging.Logger] = logging.getLogger(__name__)


def fetch_server_templates() -> list[str]:
    """Queries background infrastructure server for sorted document layouts."""
    fallback_templates: Final[list[str]] = ["README", "DMP"]
    try:
        response = requests.get(f"{BACKEND_URL}/api/templates", timeout=5)
    except requests.exceptions.ConnectionError as connection_failure:
        logger.warning(
            f"Network transport down: defaulting configurations. {connection_failure}"
        )
        return fallback_templates
    except requests.exceptions.Timeout as timeout_failure:
        logger.warning(f"Request timed out. {timeout_failure}")
        return fallback_templates
    except requests.exceptions.RequestException as generic_network_failure:
        logger.warning(f"General network failure. {generic_network_failure}")
        return fallback_templates

    if response.status_code != 200:
        return fallback_templates

    raw_templates = cast(list[str], response.json())
    sorted_templates = [
        template_name
        for template_name in TEMPLATE_SORT_ORDER
        if template_name in raw_templates
    ]
    unsorted_templates = [
        template_name
        for template_name in raw_templates
        if template_name not in TEMPLATE_SORT_ORDER
    ]
    return sorted_templates + unsorted_templates


def get_task_profile(*, task_identifier: TaskId) -> TaskProfileDict | None:
    """Tracks real-time database modifications for a running tracking ticket."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks/{task_identifier}", timeout=5)
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    return cast(TaskProfileDict, response.json())


def fetch_all_historical_tasks() -> list[dict[str, object]]:
    """Fetches all tracking records stored within backend relational layers."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/tasks", timeout=10)
    except requests.exceptions.ConnectionError:
        return []
    except requests.exceptions.Timeout:
        return []
    except requests.exceptions.RequestException:
        return []

    if response.status_code != 200:
        return []

    return cast(list[dict[str, object]], response.json())


def update_task_report(
    *,
    task_identifier: str,
    extracted_answers: dict[str, str],
    missing_information: list[str],
) -> bool:
    """Commits user manual override updates back into database storage fields."""
    update_payload: Final[dict[str, dict[str, str] | list[str]]] = {
        "extracted_answers": extracted_answers,
        "missing_information": missing_information,
    }

    try:
        response = requests.patch(
            f"{BACKEND_URL}/api/tasks/{task_identifier}/report",
            json=update_payload,
            timeout=5,
        )
    except requests.exceptions.ConnectionError as connection_failure:
        logger.error(f"Failed to update task report record maps: {connection_failure}")
        return False
    except requests.exceptions.Timeout as timeout_failure:
        logger.error(f"Timeout updating task report record maps: {timeout_failure}")
        return False
    except requests.exceptions.RequestException as generic_network_failure:
        logger.error(f"Network error updating task report: {generic_network_failure}")
        return False

    return response.status_code == 200


def extract_template_questions(file_bytes: bytes, file_name: str) -> list[str] | None:
    """Sends a template file to the backend to extract questions."""
    upload_files_payload = {"file": (file_name, file_bytes)}

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/templates/extract",
            files=upload_files_payload,
            timeout=30,
        )
    except requests.exceptions.ConnectionError as connection_failure:
        logger.error(f"Network error during template extraction: {connection_failure}")
        return None
    except requests.exceptions.Timeout as timeout_failure:
        logger.error(f"Timeout during template extraction: {timeout_failure}")
        return None
    except requests.exceptions.RequestException as generic_network_failure:
        logger.error(
            f"General network error during extraction: {generic_network_failure}"
        )
        return None

    if response.status_code != 200:
        logger.error(f"Failed to extract questions: {response.text}")
        return None

    return cast(list[str], response.json())


def create_custom_template(
    template_name: str, template_questions: list[str], template_description: str = ""
) -> bool:
    """Saves a new custom form template to the backend database."""
    creation_payload = {
        "name": template_name,
        "description": template_description,
        "questions": template_questions,
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/templates", json=creation_payload, timeout=10
        )
    except requests.exceptions.ConnectionError as connection_failure:
        logger.error(f"Network error creating template: {connection_failure}")
        return False
    except requests.exceptions.Timeout as timeout_failure:
        logger.error(f"Timeout creating template: {timeout_failure}")
        return False
    except requests.exceptions.RequestException as generic_network_failure:
        logger.error(f"General error creating template: {generic_network_failure}")
        return False

    if response.status_code != 201:
        logger.error(f"Failed to create template: {response.text}")
        return False

    return True


def generate_api_token() -> str | None:
    """Requests a new authentication token from the backend for CLI usage."""
    try:
        response = requests.post(f"{BACKEND_URL}/api/auth/token", timeout=5)
    except requests.exceptions.ConnectionError as connection_failure:
        logger.error(f"Network error generating token: {connection_failure}")
        return None
    except requests.exceptions.Timeout as timeout_failure:
        logger.error(f"Timeout generating token: {timeout_failure}")
        return None
    except requests.exceptions.RequestException as generic_network_failure:
        logger.error(f"General error generating token: {generic_network_failure}")
        return None

    if response.status_code != 201:
        logger.error(f"Failed to generate token: {response.text}")
        return None

    payload: dict[str, str] = response.json()
    return payload.get("token")


def approve_pending_update(task_identifier: str) -> bool:
    """Approves a version update and triggers the AI background generation."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tasks/{task_identifier}/approve", timeout=10
        )
    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.RequestException:
        return False

    return response.status_code == 202


def fetch_pending_context(task_identifier: str) -> dict[str, str] | None:
    """Fetches the previous and incoming metadata strings for side-by-side review."""
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/tasks/{task_identifier}/pending-context", timeout=10
        )
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    return cast(dict[str, str], response.json())

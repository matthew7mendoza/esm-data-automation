"""
Module for formatting the output and either saving locally or publishing
to the REST API.
"""

import logging
from pathlib import Path
from typing import Any, Final

import requests
import yaml

logger: Final[logging.Logger] = logging.getLogger(__name__)


def write_yaml_locally(output_path: Path, payload: dict[str, Any]) -> bool:
    """
    Writes the dictionary payload to a local YAML file safely.
    """
    logger.info(f"Writing project summary to local file: {output_path}")
    try:
        with open(output_path, mode="w", encoding="utf-8") as file_handle:
            yaml.dump(payload, file_handle, sort_keys=False, default_flow_style=False)
        logger.info("Successfully wrote YAML file.")
        return True
    except PermissionError as permission_error:
        logger.error(f"Permission denied writing to {output_path}: {permission_error}")
        return False
    except OSError as os_error:
        logger.error(f"Failed to write local YAML file: {os_error}")
        return False


def publish_to_api(  # noqa: C901
    api_endpoint: str, payload_data: dict[str, Any], output_path: Path
) -> bool:
    """
    Simulates writing a local file, then pushes that file to the FastAPI backend.
    """
    logger.info(f"Attempting to publish payload to API endpoint: {api_endpoint}")

    # We must write it locally first so we can attach it as a file upload
    write_success = write_yaml_locally(output_path=output_path, payload=payload_data)
    if not write_success:
        logger.error("Cannot publish to API because local file creation failed.")
        return False

    logger.info("Local file ready. Preparing network request.")

    try:
        with open(output_path, mode="rb") as file_to_upload:
            files_payload = {
                "files": (output_path.name, file_to_upload, "application/x-yaml")
            }
            form_data = {
                "target_doc": "DMP",
                "model_provider": "gemini",
                "custom_name": payload_data.get("experiment_name", "Published Run"),
            }

            logger.info("Executing POST request to backend...")
            response = requests.post(
                api_endpoint, data=form_data, files=files_payload, timeout=30
            )

            if response.status_code in (200, 202):
                logger.info(
                    "Successfully published to backend. HTTP Status: "
                    f"{response.status_code}"
                )
                # The response contains the task ID, which we could parse
                # and show to the user
                task_id = response.json().get("task_id", "unknown")
                logger.info(
                    f"Task successfully registered on server. Task ID: {task_id}"
                )
                return True

            logger.error(
                f"Backend rejected payload. Status: {response.status_code}. "
                f"Response: {response.text}"
            )
            return False

    except requests.exceptions.ConnectionError as connection_error:
        logger.error(
            f"Could not connect to backend server at {api_endpoint}: {connection_error}"
        )
        return False
    except requests.exceptions.Timeout as timeout_error:
        logger.error(f"Connection timed out waiting for backend: {timeout_error}")
        return False
    except requests.exceptions.RequestException as general_network_error:
        logger.error(f"General network error during publish: {general_network_error}")
        return False

"""
Module for formatting the output and either saving locally or publishing
to the REST API.
"""

import json
import logging
from pathlib import Path
from typing import Final

import requests
import yaml

logger: Final[logging.Logger] = logging.getLogger(__name__)


def write_yaml_locally(
    output_path: Path, payload_dictionary: dict[str, object]
) -> bool:
    """
    Writes the dictionary payload to a local YAML file safely.
    """
    logger.info(f"Writing project summary to local file: {output_path}")
    try:
        with open(output_path, mode="w", encoding="utf-8") as file_handle:
            yaml.dump(
                payload_dictionary,
                file_handle,
                sort_keys=False,
                default_flow_style=False,
            )
        logger.info("Successfully wrote YAML file.")
        return True
    except PermissionError as permission_error:
        logger.error(f"Permission denied writing to {output_path}: {permission_error}")
        return False
    except OSError as os_error:
        logger.error(f"Failed to write local YAML file: {os_error}")
        return False


def publish_to_api(  # noqa: C901
    api_endpoint_string: str,
    dashboard_endpoint_string: str,
    payload_dictionary: dict[str, object],
    output_file_path: Path,
    prompt_file_path: Path | None = None,
    model_provider_string: str = "gemini",
    target_document_string: str = "DMP",
) -> bool:
    """
    Simulates writing a local file, then pushes that file to the FastAPI backend.
    """
    logger.info(f"Attempting to publish payload to API endpoint: {api_endpoint_string}")

    write_success_boolean: bool = write_yaml_locally(
        output_path=output_file_path, payload_dictionary=payload_dictionary
    )
    if not write_success_boolean:
        logger.error("Cannot publish to API because local file creation failed.")
        return False

    logger.info("Local file ready. Preparing network request.")

    try:
        yaml_bytes_content: bytes = output_file_path.read_bytes()
    except OSError as read_error:
        logger.error(f"Could not read generated YAML file: {read_error}")
        return False

    files_payload_list: list[tuple[str, tuple[str, bytes, str]]] = [
        ("files", (output_file_path.name, yaml_bytes_content, "application/x-yaml"))
    ]

    if prompt_file_path is not None and prompt_file_path.exists():
        try:
            prompt_file_bytes: bytes = prompt_file_path.read_bytes()
            files_payload_list.append(
                ("files", ("custom_instructions.txt", prompt_file_bytes, "text/plain"))
            )
        except OSError as read_error:
            logger.error(f"Could not read prompt file: {read_error}")

    experiment_name_string: str = str(
        payload_dictionary.get("experiment_name", "Published Run")
    )

    form_data_dictionary: dict[str, str] = {
        "target_doc": target_document_string,
        "model_provider": model_provider_string,
        "custom_name": experiment_name_string,
    }

    config_file_path: Path = Path.home() / ".esm-tracker-config"
    if not config_file_path.exists():
        logger.error(
            "Authentication failed: ~/.esm-tracker-config not found. "
            "Please run 'esm-tracker init --token <TOKEN>' to authenticate."
        )
        return False

    try:
        with open(config_file_path, encoding="utf-8") as file_handle:
            config_data_dictionary: dict[str, str] = json.load(file_handle)
    except OSError as read_error:
        logger.error(f"Failed to read authentication configuration: {read_error}")
        return False
    except json.JSONDecodeError as json_error:
        logger.error(f"Failed to parse authentication configuration: {json_error}")
        return False

    api_token_string: str | None = config_data_dictionary.get("api_token")
    if not api_token_string:
        logger.error("Authentication failed: 'api_token' not found in configuration.")
        return False

    request_headers_dictionary: dict[str, str] = {
        "Authorization": f"Bearer {api_token_string}"
    }

    logger.info("Executing POST request to backend API...")
    try:
        network_response: requests.Response = requests.post(
            api_endpoint_string,
            data=form_data_dictionary,
            files=files_payload_list,
            headers=request_headers_dictionary,
            timeout=30,
        )
    except requests.exceptions.ConnectionError as connection_error:
        logger.error(f"Could not connect to {api_endpoint_string}: {connection_error}")
        return False
    except requests.exceptions.Timeout as timeout_error:
        logger.error(f"Connection timed out waiting for backend: {timeout_error}")
        return False
    except requests.exceptions.RequestException as general_network_error:
        logger.error(f"General network error during publish: {general_network_error}")
        return False

    if network_response.status_code not in (200, 202):
        logger.error(
            f"Backend rejected payload. Status: {network_response.status_code}. "
            f"Response: {network_response.text}"
        )
        return False

    logger.info(f"Publish successful. HTTP Status: {network_response.status_code}")

    # We must type ignore here as json() returns Any
    task_id_string: str = str(network_response.json().get("task_id", "unknown"))

    logger.info(
        f"Task successfully registered on server. Task ID: {task_id_string}\n"
        f"View your live automated document at: "
        f"{dashboard_endpoint_string}/?task_id={task_id_string}"
    )

    return True


def update_api_settings(
    api_endpoint_string: str,
    api_key_string: str,
    provider_type_string: str,
    key_name_string: str,
) -> bool:
    """
    Configures the central backend to accept a custom LLM API key.
    """
    settings_endpoint_string: str = api_endpoint_string.replace(
        "/api/generate", "/api/settings"
    )
    logger.info(f"Sending API configuration update to {settings_endpoint_string}...")

    payload_dictionary: dict[str, str] = {
        "api_key_input": api_key_string,
        "recognized_provider": provider_type_string,
        "custom_key_name": key_name_string,
    }

    try:
        network_response: requests.Response = requests.patch(
            settings_endpoint_string, json=payload_dictionary, timeout=10
        )
    except requests.exceptions.RequestException as network_error:
        logger.error(f"Network error while configuring API settings: {network_error}")
        return False

    if network_response.status_code != 200:
        logger.error(
            f"Update failed. HTTP {network_response.status_code}: "
            f"{network_response.text}"
        )
        return False

    logger.info(
        f"Successfully registered custom API key '{key_name_string}' on backend."
    )
    return True

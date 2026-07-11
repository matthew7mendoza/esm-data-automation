"""
Tests for the API publisher module.
"""

import json
import logging
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock, patch

import requests
from esm_tracker.publisher import (
    publish_to_api,
    update_api_settings,
    write_yaml_locally,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


def test_write_yaml_locally_success(tmp_path: Path) -> None:
    """Validates that YAML writing succeeds on a valid path."""
    target_file_path: Path = tmp_path / "project_summary.yaml"
    payload_dictionary: dict[str, object] = {"test_key": "test_value"}

    success_boolean: bool = write_yaml_locally(
        output_path=target_file_path, payload_dictionary=payload_dictionary
    )

    if not success_boolean:
        logger.error("Local YAML write unexpectedly failed.")

    assert success_boolean is True
    assert target_file_path.exists()


@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_success(
    mock_post_function: MagicMock, tmp_path: Path
) -> None:
    """Validates successful payload transmission to the backend."""
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.json.return_value = {"task_id": "test-task-123"}
    mock_post_function.return_value = mock_response

    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    payload_dictionary: dict[str, object] = {"experiment_name": "Test Run"}

    config_file_path: Path = tmp_path / ".esm-tracker-config"
    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        config_file_path.write_text(json.dumps({"api_token": "secure-token-abc"}))

        success_boolean: bool = publish_to_api(
            api_endpoint_string="http://fake-api/generate",
            dashboard_endpoint_string="http://fake-dash",
            payload_dictionary=payload_dictionary,
            output_file_path=output_yaml_path,
        )

    if not success_boolean:
        logger.error("Publish unexpectedly failed on valid network response.")

    assert success_boolean is True
    mock_post_function.assert_called_once()


@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_network_failure(
    mock_post_function: MagicMock, tmp_path: Path
) -> None:
    """Validates resilient failure handling when the network drops."""
    mock_post_function.side_effect = requests.exceptions.ConnectionError("Down")

    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    payload_dictionary: dict[str, object] = {"experiment_name": "Test Run"}

    config_file_path: Path = tmp_path / ".esm-tracker-config"
    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        config_file_path.write_text(json.dumps({"api_token": "secure-token-abc"}))

        success_boolean: bool = publish_to_api(
            api_endpoint_string="http://fake-api/generate",
            dashboard_endpoint_string="http://fake-dash",
            payload_dictionary=payload_dictionary,
            output_file_path=output_yaml_path,
        )

    if success_boolean:
        logger.error("Publish unexpectedly succeeded despite network failure.")

    assert success_boolean is False


@patch("esm_tracker.publisher.requests.patch")
def test_update_api_settings_success(mock_patch_function: MagicMock) -> None:
    """Validates settings transmission to the backend."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_patch_function.return_value = mock_response

    success_boolean: bool = update_api_settings(
        api_endpoint_string="http://fake/api/generate",
        api_key_string="test-key",
        provider_type_string="openai",
        key_name_string="TestKey",
    )

    if not success_boolean:
        logger.error("Settings update unexpectedly failed.")

    assert success_boolean is True
    mock_patch_function.assert_called_once()

def test_write_yaml_locally_permission_error(tmp_path: Path) -> None:
    target_file_path: Path = tmp_path / "project_summary.yaml"
    with patch("esm_tracker.publisher.open", side_effect=PermissionError("Denied")):
        assert write_yaml_locally(target_file_path, {"test": "val"}) is False

def test_write_yaml_locally_os_error(tmp_path: Path) -> None:
    target_file_path: Path = tmp_path / "project_summary.yaml"
    with patch("esm_tracker.publisher.open", side_effect=OSError("OS Error")):
        assert write_yaml_locally(target_file_path, {"test": "val"}) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_missing_config(_mock_post: MagicMock, tmp_path: Path) -> None:
    output_yaml_path: Path = tmp_path / "project_summary.yaml"

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_malformed_config(_mock_post: MagicMock, tmp_path: Path) -> None:
    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        config_file_path.write_text("invalid json {")
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_os_error_on_config_read(
    _mock_post: MagicMock, tmp_path: Path
) -> None:
    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"
    config_file_path.write_text("{}")

    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
        patch("esm_tracker.publisher.open", side_effect=OSError("Read Err")),
    ):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
            ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_no_token(_mock_post: MagicMock, tmp_path: Path) -> None:
    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"
    config_file_path.write_text(json.dumps({"wrong_key": "abc"}))

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_timeout(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = requests.exceptions.Timeout("Timeout")
    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"
    config_file_path.write_text(json.dumps({"api_token": "abc"}))

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_request_exception(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_post.side_effect = requests.exceptions.RequestException("RequestException")
    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"
    config_file_path.write_text(json.dumps({"api_token": "abc"}))

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_bad_status(mock_post: MagicMock, tmp_path: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_post.return_value = mock_response

    output_yaml_path: Path = tmp_path / "project_summary.yaml"
    config_file_path: Path = tmp_path / ".esm-tracker-config"
    config_file_path.write_text(json.dumps({"api_token": "abc"}))

    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api(
            "http://fake", "http://dash", {"k": "v"}, output_yaml_path
        ) is False

@patch("esm_tracker.publisher.requests.patch")
def test_update_api_settings_request_exception(mock_patch: MagicMock) -> None:
    mock_patch.side_effect = requests.exceptions.RequestException("RequestException")
    assert update_api_settings("http://fake", "key", "openai", "Test") is False

def test_publish_to_api_yaml_read_error(tmp_path: Path) -> None:
    yaml_path = tmp_path / "test.yaml"
    with patch(
        "esm_tracker.publisher.Path.read_bytes", side_effect=OSError("Read err")
    ):
        assert publish_to_api("http", "http", {}, yaml_path) is False

@patch("esm_tracker.publisher.requests.post")
def test_publish_to_api_prompt_file_read_error(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    yaml_path = tmp_path / "test.yaml"
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("prompt")
    config = tmp_path / ".esm-tracker-config"
    config.write_text('{"api_token": "abc"}')
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.json.return_value = {"task_id": "123"}
    mock_post.return_value = mock_response

    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
        patch("esm_tracker.publisher.Path.read_bytes", side_effect=OSError("Err")),
    ):
        assert publish_to_api("http", "http", {}, yaml_path, prompt_path) is False

@patch("esm_tracker.publisher.requests.patch")
def test_update_api_settings_bad_status(mock_patch: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_patch.return_value = mock_response
    assert update_api_settings("http", "key", "openai", "Test") is False

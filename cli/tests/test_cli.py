"""
Tests for the core CLI module and argument parsing.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock, patch

import pytest
from esm_tracker.cli import (
    DataFileSystemEventHandler,
    execute_initialization_workflow,
    load_or_initialize_project_state,
    main,
    run_tracking_pipeline,
    save_authentication_token,
    submit_job_to_slurm_scheduler,
)
from watchdog.events import FileCreatedEvent

logger: Final[logging.Logger] = logging.getLogger(__name__)


def test_save_authentication_token_success(tmp_path: Path) -> None:
    """Validates secure token persistence."""
    with patch("esm_tracker.cli.Path.home", return_value=tmp_path):
        save_authentication_token(api_token_string="secure-123")

    config_file_path: Path = tmp_path / ".esm-tracker-config"
    assert config_file_path.exists()

    with open(config_file_path, encoding="utf-8") as file_handle:
        data_dictionary: dict[str, str] = json.load(file_handle)
        assert data_dictionary["api_token"] == "secure-123"


def test_load_or_initialize_project_state(tmp_path: Path) -> None:
    """Validates UUID generation and retrieval."""
    first_uuid_string, _, _ = load_or_initialize_project_state(
        target_directory_path=tmp_path,
        experiment_name_string="Exp",
        model_archetype_string="Mod",
    )
    assert first_uuid_string

    second_uuid_string, _, _ = load_or_initialize_project_state(
        target_directory_path=tmp_path,
        experiment_name_string="Exp",
        model_archetype_string="Mod",
    )
    if first_uuid_string != second_uuid_string:
        logger.error("UUID retrieval failed; generated a new one instead of reading.")

    assert first_uuid_string == second_uuid_string


@patch("esm_tracker.cli.subprocess.run")
def test_submit_job_to_slurm_scheduler(
    mock_run_function: MagicMock, tmp_path: Path
) -> None:
    """Validates SBATCH script generation and execution."""
    original_arguments_list: list[str] = ["esm-tracker", "init", "--slurm"]

    submit_job_to_slurm_scheduler(
        original_arguments_list=original_arguments_list, target_directory_path=tmp_path
    )

    script_file_path: Path = tmp_path / ".esm_slurm_submission.sh"
    assert script_file_path.exists()

    script_content_string: str = script_file_path.read_text()
    if "--slurm" in script_content_string:
        logger.error("SLURM flag was not safely stripped from background command.")

    assert "--slurm" not in script_content_string
    mock_run_function.assert_called_once()


@patch(
    "esm_tracker.cli.sys.argv",
    [
        "esm-tracker",
        "config",
        "--api-key",
        "test",
        "--provider",
        "openai",
        "--name",
        "Test",
    ],
)
@patch("esm_tracker.cli.update_api_settings", return_value=True)
def test_main_config_command(_mock_update_function: MagicMock) -> None:
    """Validates the config CLI path."""
    try:
        main()
    except SystemExit:
        logger.error("CLI config command unexpectedly exited.")

    _mock_update_function.assert_called_once()


@patch(
    "esm_tracker.cli.sys.argv",
    ["esm-tracker", "init", "--experiment", "Exp", "--model", "Mod"],
)
@patch("esm_tracker.cli.execute_initialization_workflow")
def test_main_init_command(_mock_execute_function: MagicMock) -> None:
    main()
    _mock_execute_function.assert_called_once()


def test_save_authentication_token_empty(tmp_path: Path) -> None:
    save_authentication_token("")
    assert not (tmp_path / ".esm-tracker-config").exists()


@patch("esm_tracker.cli.Path.write_text", side_effect=OSError("Err"))
def test_submit_job_to_slurm_scheduler_oserror(
    _mock_write: MagicMock, tmp_path: Path
) -> None:
    submit_job_to_slurm_scheduler(["esm-tracker"], tmp_path)


@patch("esm_tracker.cli.subprocess.run", side_effect=FileNotFoundError("Err"))
def test_submit_job_to_slurm_scheduler_filenotfound(
    _mock_run: MagicMock, tmp_path: Path
) -> None:
    submit_job_to_slurm_scheduler(["esm-tracker"], tmp_path)


@patch(
    "esm_tracker.cli.subprocess.run",
    side_effect=subprocess.CalledProcessError(1, "sbatch"),
)
def test_submit_job_to_slurm_scheduler_calledprocesserror(
    _mock_run: MagicMock, tmp_path: Path
) -> None:
    submit_job_to_slurm_scheduler(["esm-tracker"], tmp_path)


@patch("esm_tracker.cli.scan_directory", return_value=[])
@patch("esm_tracker.cli.write_yaml_locally")
def test_run_tracking_pipeline_no_publish(
    _mock_write: MagicMock, _mock_scan: MagicMock, tmp_path: Path
) -> None:
    run_tracking_pipeline(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        project_unique_identifier_string="uuid",
        is_force_update_boolean=False,
        publish_boolean_flag=False,
        api_endpoint_string="http://api",
        dashboard_endpoint_string="http://dash",
    )
    _mock_write.assert_called_once()


@patch("esm_tracker.cli.scan_directory", return_value=[{"file_name": "x"}])
@patch("esm_tracker.cli.publish_to_api", return_value=True)
def test_run_tracking_pipeline_publish(
    _mock_pub: MagicMock, _mock_scan: MagicMock, tmp_path: Path
) -> None:
    run_tracking_pipeline(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        project_unique_identifier_string="uuid",
        is_force_update_boolean=False,
        publish_boolean_flag=True,
        api_endpoint_string="http://api",
        dashboard_endpoint_string="http://dash",
    )
    _mock_pub.assert_called_once()


@patch("esm_tracker.cli.run_tracking_pipeline")
def test_data_file_system_event_handler(mock_pipe: MagicMock) -> None:
    handler = DataFileSystemEventHandler({"test": "val"})
    handler.on_created(FileCreatedEvent("/fake/test.nc"))
    mock_pipe.assert_called_once()


@patch("esm_tracker.cli.uuid.uuid4", return_value="fake-uuid")
def test_load_or_initialize_project_state_read_err(
    _mock_uuid: MagicMock, tmp_path: Path
) -> None:
    p = tmp_path / ".esm_tracker_id.json"
    p.write_text("{invalid")
    uuid_str, _, _ = load_or_initialize_project_state(
        target_directory_path=tmp_path,
        experiment_name_string="Exp",
        model_archetype_string="Mod",
    )
    assert uuid_str == "fake-uuid"


@patch("esm_tracker.cli.uuid.uuid4", return_value="fake-uuid")
def test_load_or_initialize_project_state_write_err(
    _mock_uuid: MagicMock, tmp_path: Path
) -> None:
    with patch("builtins.open", side_effect=OSError("Err")), pytest.raises(SystemExit):
        load_or_initialize_project_state(
            target_directory_path=tmp_path,
            experiment_name_string="Exp",
            model_archetype_string="Mod",
        )


@patch("esm_tracker.cli.submit_job_to_slurm_scheduler")
def test_execute_initialization_workflow_slurm(
    mock_submit: MagicMock, tmp_path: Path
) -> None:
    execute_initialization_workflow(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        watch_boolean_flag=False,
        slurm_boolean_flag=False,
        publish_boolean_flag=True,
        include_pattern_string="*",
        exclude_pattern_string="",
    )
    mock_submit.assert_called_once()


@patch("esm_tracker.cli.run_tracking_pipeline")
@patch(
    "esm_tracker.cli.load_or_initialize_project_state",
    return_value=("uuid", "Exp", "Mod"),
)
def test_execute_initialization_workflow_no_watch(
    _mock_uuid: MagicMock, mock_pipe: MagicMock, tmp_path: Path
) -> None:
    execute_initialization_workflow(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        watch_boolean_flag=False,
        slurm_boolean_flag=False,
        publish_boolean_flag=False,
        include_pattern_string="*",
        exclude_pattern_string="",
    )
    mock_pipe.assert_called_once()


@patch("esm_tracker.cli.Observer")
@patch("esm_tracker.cli.run_tracking_pipeline")
@patch(
    "esm_tracker.cli.load_or_initialize_project_state",
    return_value=("uuid", "Exp", "Mod"),
)
@patch("esm_tracker.cli.time.sleep", side_effect=KeyboardInterrupt)
def test_execute_initialization_workflow_watch(
    _mock_sleep: MagicMock,
    _mock_uuid: MagicMock,
    _mock_pipe: MagicMock,
    mock_obs: MagicMock,
    tmp_path: Path,
) -> None:
    execute_initialization_workflow(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        watch_boolean_flag=True,
        slurm_boolean_flag=False,
        publish_boolean_flag=False,
        include_pattern_string="*",
        exclude_pattern_string="",
    )
    mock_obs.return_value.start.assert_called_once()


@patch("esm_tracker.cli.scan_directory", return_value=[{"file_name": "x"}])
@patch("esm_tracker.cli.publish_to_api", return_value=False)
def test_run_tracking_pipeline_publish_fails(
    _mock_pub: MagicMock, _mock_scan: MagicMock, tmp_path: Path
) -> None:
    run_tracking_pipeline(
        experiment_name_string="Exp",
        model_archetype_string="Mod",
        target_directory_path=tmp_path,
        project_unique_identifier_string="uuid",
        is_force_update_boolean=False,
        publish_boolean_flag=True,
        api_endpoint_string="http",
        dashboard_endpoint_string="http",
    )
    _mock_pub.assert_called_once()


@patch("esm_tracker.cli.run_tracking_pipeline")
def test_data_file_system_event_handler_ignore(mock_pipe: MagicMock) -> None:
    handler = DataFileSystemEventHandler({})
    handler.on_created(FileCreatedEvent("/fake/test.txt"))
    mock_pipe.assert_not_called()


@patch(
    "esm_tracker.cli.sys.argv",
    ["esm-tracker", "config", "--api-key", "a", "--provider", "p", "--name", "n"],
)
@patch("esm_tracker.cli.update_api_settings", return_value=False)
def test_main_config_fail(_mock_update: MagicMock) -> None:
    with pytest.raises(SystemExit):
        main()


@patch(
    "esm_tracker.cli.sys.argv",
    [
        "esm-tracker",
        "init",
        "--experiment",
        "e",
        "--model",
        "m",
        "--prompt-file",
        "/invalid/path/does/not/exist",
    ],
)
def test_main_init_invalid_prompt() -> None:
    with pytest.raises(SystemExit):
        main()


@patch(
    "esm_tracker.cli.sys.argv",
    [
        "esm-tracker",
        "run",
        "--experiment",
        "e",
        "--model",
        "m",
        "--force-update",
        "--token",
        "tok",
    ],
)
@patch("esm_tracker.cli.execute_initialization_workflow")
@patch("esm_tracker.cli.save_authentication_token")
def test_main_run_force_token(mock_save: MagicMock, mock_exec: MagicMock) -> None:
    main()
    mock_save.assert_called_with("tok")
    mock_exec.assert_called_once()

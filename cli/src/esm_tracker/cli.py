"""
Main command line interface entrypoint for esm-tracker.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Final

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from esm_tracker.publisher import publish_to_api, write_yaml_locally
from esm_tracker.scanner import FileMetadata, scan_directory

logger: Final[logging.Logger] = logging.getLogger("esm_tracker")


def save_authentication_token(api_token_string: str) -> None:
    """Saves the API token securely to the user's home directory."""
    if not api_token_string:
        logger.error("Failed to save token: Provided token string is empty.")
        return

    config_file_path: Path = Path.home() / ".esm-tracker-config"
    config_data_dictionary: dict[str, str] = {"api_token": api_token_string}

    try:
        with open(config_file_path, "w", encoding="utf-8") as file_handle:
            json.dump(config_data_dictionary, file_handle)
        config_file_path.chmod(0o600)
        logger.info(
            f"Successfully saved secure authentication token to {config_file_path}"
        )
    except OSError as write_error:
        logger.error(f"Failed to write authentication token: {write_error}")


def configure_logging() -> None:
    """Sets up highly descriptive console logging for interns and scientists."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def submit_job_to_slurm_scheduler(
    original_arguments_list: list[str], target_directory_path: Path
) -> None:
    """Generates an sbatch script and offloads the scanning process to a SLURM node."""
    logger.info("Preparing to submit background job to SLURM scheduler.")

    safe_arguments_list: list[str] = [
        argument for argument in original_arguments_list if argument != "--slurm"
    ]
    command_string: str = " ".join(safe_arguments_list)

    hidden_directory_path: Path = target_directory_path / ".esm"
    hidden_directory_path.mkdir(parents=True, exist_ok=True)
    script_file_path: Path = hidden_directory_path / ".esm_slurm_submission.sh"

    script_content_string: str = (
        "#!/bin/bash\n"
        "#SBATCH --job-name=esm-tracker-scan\n"
        "#SBATCH --time=01:00:00\n"
        "#SBATCH --nodes=1\n"
        "#SBATCH --ntasks=1\n"
        "#SBATCH --cpus-per-task=8\n\n"
        f"{command_string}\n"
    )

    try:
        script_file_path.write_text(script_content_string, encoding="utf-8")
        logger.info(
            f"Successfully wrote SLURM submission script to {script_file_path}."
        )
    except OSError as os_error:
        logger.error(f"Operating system error writing SLURM script: {os_error}")
        return

    try:
        subprocess.run(["sbatch", str(script_file_path)], check=True)
        logger.info("Successfully submitted background job to SLURM scheduler.")
    except FileNotFoundError:
        logger.error("The 'sbatch' command was not found. Are you on a SLURM node?")
    except subprocess.CalledProcessError as process_error:
        logger.error(
            f"Failed to submit SLURM job. Process exited with error: {process_error}"
        )


def run_tracking_pipeline(
    experiment_name_string: str,
    model_archetype_string: str,
    target_directory_path: Path,
    project_unique_identifier_string: str,
    is_force_update_boolean: bool,
    publish_boolean_flag: bool,
    api_endpoint_string: str,
    dashboard_endpoint_string: str,
    include_pattern_string: str = "*",
    exclude_pattern_string: str = "",
) -> None:
    """
    Coordinates the scanning and publishing workflow using strictly flat logic.
    """
    logger.info(
        f"Tracking experiment: {experiment_name_string} | "
        f"Model: {model_archetype_string}"
    )

    extracted_datasets_list: list[FileMetadata] = scan_directory(
        target_directory_path=target_directory_path,
        include_pattern_string=include_pattern_string,
        exclude_pattern_string=exclude_pattern_string,
    )

    if not extracted_datasets_list:
        logger.error(
            f"No NetCDF (.nc) or Zarr data found in {target_directory_path}. "
            "Are you in the right directory?"
        )
        sys.exit(1)

    project_summary_payload_dictionary: dict[str, object] = {
        "project_unique_identifier": project_unique_identifier_string,
        "is_force_update_boolean": is_force_update_boolean,
        "experiment_name": experiment_name_string,
        "model_archetype": model_archetype_string,
        "datasets": extracted_datasets_list,
    }

    output_yaml_file_path: Path = target_directory_path / "project_summary.yaml"

    if not publish_boolean_flag:
        logger.info("No publish flag detected. Saving local YAML only.")
        write_yaml_locally(
            output_path=output_yaml_file_path,
            payload_dictionary=project_summary_payload_dictionary,
        )
        logger.info(
            f"Success! 📄 project_summary.yaml generated at {output_yaml_file_path}"
        )
        return

    logger.info(f"Publish flag detected. Will attempt to send to {api_endpoint_string}")

    publish_success_boolean: bool = publish_to_api(
        api_endpoint_string=api_endpoint_string,
        dashboard_endpoint_string=dashboard_endpoint_string,
        payload_dictionary=project_summary_payload_dictionary,
        output_file_path=output_yaml_file_path,
    )

    if publish_success_boolean:
        logger.info(
            "Publishing workflow complete successfully. Check the web dashboard!"
        )
        return

    logger.error("Publishing workflow failed. Local YAML file is still available.")


class DataFileSystemEventHandler(FileSystemEventHandler):
    """Watches for newly created data files to trigger the automated pipeline."""

    def __init__(
        self, pipeline_keyword_arguments_dictionary: dict[str, object]
    ) -> None:
        super().__init__()
        self.pipeline_keyword_arguments_dictionary = (
            pipeline_keyword_arguments_dictionary
        )

    def on_created(self, event: FileSystemEvent) -> None:
        file_path_string: str = str(event.src_path)

        is_netcdf_file_boolean: bool = (
            not event.is_directory and file_path_string.endswith(".nc")
        )
        is_zarr_directory_boolean: bool = (
            event.is_directory and file_path_string.endswith(".zarr")
        )

        if not (is_netcdf_file_boolean or is_zarr_directory_boolean):
            return

        logger.info(
            f"New data successfully detected by background process: {file_path_string}"
        )
        run_tracking_pipeline(**self.pipeline_keyword_arguments_dictionary)  # type: ignore


def load_or_initialize_project_state(
    target_directory_path: Path,
    experiment_name_string: str | None,
    model_archetype_string: str | None,
) -> tuple[str, str, str]:
    """Retrieves existing project state or initializes a new one."""
    hidden_directory_path: Path = target_directory_path / ".esm"
    hidden_directory_path.mkdir(parents=True, exist_ok=True)

    identifier_file_path: Path = hidden_directory_path / ".esm_tracker_id.json"

    if identifier_file_path.exists():
        try:
            with open(identifier_file_path, encoding="utf-8") as file_handle:
                data_dictionary: dict[str, str] = json.load(file_handle)
                project_id_string: str = data_dictionary["project_unique_identifier"]
                saved_experiment_string: str = data_dictionary["experiment_name"]
                saved_model_string: str = data_dictionary["model_archetype"]
                return project_id_string, saved_experiment_string, saved_model_string
        except (OSError, json.JSONDecodeError, KeyError) as read_error:
            logger.error(
                f"Failed to read existing project state: {read_error}. Re-initializing."
            )

    if experiment_name_string is None or model_archetype_string is None:
        logger.error(
            "Project state not found. You must run 'init' with "
            "--experiment and --model first."
        )
        sys.exit(1)

    new_uuid_string: str = str(uuid.uuid4())
    state_dictionary: dict[str, str] = {
        "project_unique_identifier": new_uuid_string,
        "experiment_name": experiment_name_string,
        "model_archetype": model_archetype_string,
    }

    try:
        with open(identifier_file_path, "w", encoding="utf-8") as file_handle:
            json.dump(state_dictionary, file_handle)
        logger.info(f"Initialized new project state with UUID: {new_uuid_string}")
    except OSError as write_error:
        logger.error(f"Could not save project state: {write_error}")
        sys.exit(1)

    return new_uuid_string, experiment_name_string, model_archetype_string


def execute_initialization_workflow(
    experiment_name_string: str | None,
    model_archetype_string: str | None,
    target_directory_path: Path,
    watch_boolean_flag: bool,
    slurm_boolean_flag: bool,
    publish_boolean_flag: bool,
    include_pattern_string: str,
    exclude_pattern_string: str,
    is_force_update_boolean: bool = False,
) -> None:
    """Sets up the execution environment (single-run, watch mode, or SLURM)."""
    if slurm_boolean_flag:
        submit_job_to_slurm_scheduler(
            original_arguments_list=sys.argv,
            target_directory_path=target_directory_path,
        )
        return

    api_endpoint_string: str = os.environ.get(
        "ESM_TRACKER_API_URL", "http://localhost:8000/api/generate"
    )

    dashboard_endpoint_string: str = os.environ.get(
        "ESM_TRACKER_DASHBOARD_URL", "http://localhost:8501"
    )

    project_id, active_experiment, active_model = load_or_initialize_project_state(
        target_directory_path=target_directory_path,
        experiment_name_string=experiment_name_string,
        model_archetype_string=model_archetype_string,
    )

    pipeline_keyword_arguments_dictionary: dict[str, object] = {
        "experiment_name_string": active_experiment,
        "model_archetype_string": active_model,
        "target_directory_path": target_directory_path,
        "project_unique_identifier_string": project_id,
        "is_force_update_boolean": is_force_update_boolean,
        "publish_boolean_flag": publish_boolean_flag,
        "api_endpoint_string": api_endpoint_string,
        "dashboard_endpoint_string": dashboard_endpoint_string,
        "include_pattern_string": include_pattern_string,
        "exclude_pattern_string": exclude_pattern_string,
    }

    run_tracking_pipeline(**pipeline_keyword_arguments_dictionary)  # type: ignore

    if not watch_boolean_flag:
        return

    logger.info("Background watch mode enabled. Waiting for new data files...")

    file_system_event_handler = DataFileSystemEventHandler(
        pipeline_keyword_arguments_dictionary=pipeline_keyword_arguments_dictionary
    )
    directory_observer = Observer()
    directory_observer.schedule(
        file_system_event_handler, str(target_directory_path), recursive=True
    )
    directory_observer.start()

    logger.info(
        f"Background observer successfully scheduled on {target_directory_path}."
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info(
            "Background watch manually interrupted. Shutting down observer gracefully."
        )
        directory_observer.stop()

    directory_observer.join()
    logger.info("Background observer shutdown complete successfully.")


def setup_argument_parser() -> argparse.ArgumentParser:
    command_line_argument_parser = argparse.ArgumentParser(
        description="ESM Data Automation Tracker - Scans NetCDF and Zarr metadata."
    )

    sub_parsers = command_line_argument_parser.add_subparsers(
        dest="command", required=True
    )

    initialization_parser = sub_parsers.add_parser(
        "init", help="Initialize a new experiment tracking sequence."
    )
    initialization_parser.add_argument(
        "--experiment", required=True, type=str, help="Name of the experiment to track."
    )
    initialization_parser.add_argument(
        "--model", required=True, type=str, help="Model archetype (e.g. 'GFDL SPEAR')."
    )
    initialization_parser.add_argument(
        "--token",
        type=str,
        help="Secure API token generated from the Streamlit frontend.",
    )

    def add_common_tracking_args(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument(
            "--publish",
            action="store_true",
            help="Publish the generated YAML straight to the API.",
        )
        parser_obj.add_argument(
            "--watch",
            action="store_true",
            help="Run in background and automatically refresh on new files.",
        )
        parser_obj.add_argument(
            "--slurm",
            action="store_true",
            help="Submit this tracking job to the SLURM scheduler via sbatch.",
        )
        parser_obj.add_argument(
            "--directory",
            type=str,
            default=".",
            help="Target directory to scan. Defaults to current working directory.",
        )
        parser_obj.add_argument(
            "--include",
            type=str,
            default="*",
            help="Glob pattern to include files (e.g. '*_monthly.nc').",
        )
        parser_obj.add_argument(
            "--exclude",
            type=str,
            default="",
            help="Glob pattern to exclude files (e.g. '*restart*').",
        )

    add_common_tracking_args(initialization_parser)

    run_parser = sub_parsers.add_parser(
        "run", help="Run the tracker to update an existing project."
    )
    add_common_tracking_args(run_parser)
    run_parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force an update and queue for review.",
    )

    return command_line_argument_parser


def process_command_execution(parsed_arguments_namespace: argparse.Namespace) -> None:

    if parsed_arguments_namespace.command in ["init", "run"]:
        target_directory_path: Path = Path(
            parsed_arguments_namespace.directory
        ).resolve()

        if (
            parsed_arguments_namespace.command == "init"
            and parsed_arguments_namespace.token
        ):
            save_authentication_token(parsed_arguments_namespace.token)

        is_force_update: bool = False
        experiment_name_string: str | None = None
        model_archetype_string: str | None = None

        if parsed_arguments_namespace.command == "run":
            is_force_update = parsed_arguments_namespace.force_update
        elif parsed_arguments_namespace.command == "init":
            experiment_name_string = parsed_arguments_namespace.experiment
            model_archetype_string = parsed_arguments_namespace.model

        execute_initialization_workflow(
            experiment_name_string=experiment_name_string,
            model_archetype_string=model_archetype_string,
            target_directory_path=target_directory_path,
            watch_boolean_flag=parsed_arguments_namespace.watch,
            slurm_boolean_flag=parsed_arguments_namespace.slurm,
            publish_boolean_flag=parsed_arguments_namespace.publish,
            include_pattern_string=parsed_arguments_namespace.include,
            exclude_pattern_string=parsed_arguments_namespace.exclude,
            is_force_update_boolean=is_force_update,
        )


def main() -> None:
    """Entry point execution function for the esm-tracker command line interface."""
    configure_logging()
    command_line_argument_parser = setup_argument_parser()
    parsed_arguments_namespace = command_line_argument_parser.parse_args()
    process_command_execution(parsed_arguments_namespace)


if __name__ == "__main__":
    main()

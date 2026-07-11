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

from esm_tracker.publisher import (
    publish_to_api,
    update_api_settings,
    write_yaml_locally,
)
from esm_tracker.scanner import FileMetadata, scan_directory

logger: Final[logging.Logger] = logging.getLogger("esm_tracker")


def save_authentication_token(api_token_string: str) -> None:
    """Saves the API token securely to the user's home directory."""
    if not api_token_string:
        logger.error("Failed to save token: Provided token string is empty.")
        return

    config_file_path: Path = Path.home() / ".esm-tracker-config"
    config_data: dict[str, str] = {"api_token": api_token_string}

    with open(config_file_path, "w", encoding="utf-8") as file_handle:
        json.dump(config_data, file_handle)

    config_file_path.chmod(0o600)
    logger.info(f"Successfully saved secure authentication token to {config_file_path}")


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

    script_file_path: Path = target_directory_path / ".esm_slurm_submission.sh"

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
        script_file_path.write_text(script_content_string)
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
    publish_boolean_flag: bool,
    target_directory_path: Path,
    api_endpoint_string: str,
    dashboard_endpoint_string: str,
    project_unique_identifier_string: str,
    is_force_update_boolean: bool,
    include_pattern_string: str = "*",
    exclude_pattern_string: str = "",
    prompt_file_path: Path | None = None,
    model_provider_string: str = "gemini",
    target_document_string: str = "DMP",
) -> None:
    """
    Coordinates the scanning and publishing workflow using strictly flat logic.
    """
    logger.info(
        f"Init experiment: {experiment_name_string} | Model: {model_archetype_string}"
    )

    extracted_datasets_list: list[FileMetadata] = scan_directory(
        target_directory_path=target_directory_path,
        include_pattern_string=include_pattern_string,
        exclude_pattern_string=exclude_pattern_string,
    )

    if not extracted_datasets_list:
        logger.warning("No data found. Writing empty project summary.")

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
            f"Scan finished successfully. File generated at {output_yaml_file_path}"
        )
        return

    logger.info(f"Publish flag detected. Will attempt to send to {api_endpoint_string}")

    publish_success_boolean: bool = publish_to_api(
        api_endpoint_string=api_endpoint_string,
        dashboard_endpoint_string=dashboard_endpoint_string,
        payload_dictionary=project_summary_payload_dictionary,
        output_file_path=output_yaml_file_path,
        prompt_file_path=prompt_file_path,
        model_provider_string=model_provider_string,
        target_document_string=target_document_string,
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
        # Ignore type checking here because we pass mixed types as kwargs

        run_tracking_pipeline(**self.pipeline_keyword_arguments_dictionary)  # type: ignore


def get_or_create_project_identifier(target_directory_path: Path) -> str:
    """Retrieves the existing UUID or generates a new one securely."""
    identifier_file_path: Path = target_directory_path / ".esm_tracker_id.json"
    if identifier_file_path.exists():
        try:
            with open(identifier_file_path, encoding="utf-8") as file_handle:
                data_dictionary: dict[str, str] = json.load(file_handle)
                project_id_string: str = data_dictionary["project_unique_identifier"]
                return project_id_string
        except (OSError, json.JSONDecodeError, KeyError) as read_error:
            logger.error(
                f"Failed to read existing project ID: {read_error}. Generating new one."
            )
            pass

    new_uuid_string: str = str(uuid.uuid4())
    try:
        with open(identifier_file_path, "w", encoding="utf-8") as file_handle:
            json.dump({"project_unique_identifier": new_uuid_string}, file_handle)
        logger.info(f"Generated new project unique identifier: {new_uuid_string}")
    except OSError as write_error:
        logger.error(f"Could not save project identifier: {write_error}")

    return new_uuid_string


def execute_initialization_workflow(
    experiment_name_string: str,
    model_archetype_string: str,
    publish_boolean_flag: bool,
    target_directory_path: Path,
    watch_boolean_flag: bool,
    slurm_boolean_flag: bool,
    include_pattern_string: str,
    exclude_pattern_string: str,
    is_force_update_boolean: bool = False,
    prompt_file_path: Path | None = None,
    model_provider_string: str = "gemini",
    target_document_string: str = "DMP",
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

    project_unique_identifier_string: str = get_or_create_project_identifier(
        target_directory_path=target_directory_path
    )

    pipeline_keyword_arguments_dictionary: dict[str, object] = {
        "experiment_name_string": experiment_name_string,
        "model_archetype_string": model_archetype_string,
        "publish_boolean_flag": publish_boolean_flag,
        "target_directory_path": target_directory_path,
        "api_endpoint_string": api_endpoint_string,
        "dashboard_endpoint_string": dashboard_endpoint_string,
        "project_unique_identifier_string": project_unique_identifier_string,
        "is_force_update_boolean": is_force_update_boolean,
        "include_pattern_string": include_pattern_string,
        "exclude_pattern_string": exclude_pattern_string,
        "prompt_file_path": prompt_file_path,
        "model_provider_string": model_provider_string,
        "target_document_string": target_document_string,
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


def main() -> None:  # noqa: C901
    """Entry point execution function for the esm-tracker command line interface."""
    configure_logging()

    command_line_argument_parser = argparse.ArgumentParser(
        description="ESM Data Automation Tracker - Scans NetCDF and Zarr metadata."
    )

    sub_parsers = command_line_argument_parser.add_subparsers(
        dest="command", required=True
    )

    initialization_parser = sub_parsers.add_parser(
        "init", help="Initialize a new experiment tracking sequence."
    )

    def add_common_tracking_args(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument(
            "--experiment",
            required=True,
            type=str,
            help="Name of the experiment to track.",
        )
        parser_obj.add_argument(
            "--model",
            required=True,
            type=str,
            help="Model archetype (e.g. 'GFDL SPEAR').",
        )
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
        parser_obj.add_argument(
            "--prompt-file",
            type=str,
            help="Path to a text file containing custom LLM instructions.",
        )
        parser_obj.add_argument(
            "--provider",
            type=str,
            default="gemini",
            help="The LLM provider or custom key name to use (default: gemini).",
        )
        parser_obj.add_argument(
            "--template",
            type=str,
            default="DMP",
            help="Target document template to generate (e.g., DMP). Defaults to DMP.",
        )
        parser_obj.add_argument(
            "--token",
            type=str,
            help="Secure API token generated from the Streamlit frontend.",
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

    configuration_parser = sub_parsers.add_parser(
        "config", help="Configure custom settings like API keys for the backend."
    )
    configuration_parser.add_argument(
        "--api-key", required=True, type=str, help="Your personal LLM API Key."
    )
    configuration_parser.add_argument(
        "--provider", required=True, type=str, help="Provider type (e.g. 'openai')."
    )
    configuration_parser.add_argument(
        "--name", required=True, type=str, help="Unique name for this API key mapping."
    )

    parsed_arguments_namespace = command_line_argument_parser.parse_args()

    api_endpoint_string: str = os.environ.get(
        "ESM_TRACKER_API_URL", "http://localhost:8000/api/generate"
    )

    if parsed_arguments_namespace.command == "config":
        update_success_boolean: bool = update_api_settings(
            api_endpoint_string=api_endpoint_string,
            api_key_string=parsed_arguments_namespace.api_key,
            provider_type_string=parsed_arguments_namespace.provider,
            key_name_string=parsed_arguments_namespace.name,
        )
        if not update_success_boolean:
            logger.error("API Key configuration failed.")
            sys.exit(1)

        logger.info("API Key configuration complete successfully. Ready to init.")
        return

    if parsed_arguments_namespace.command in ["init", "run"]:
        target_directory_path: Path = Path(
            parsed_arguments_namespace.directory
        ).resolve()
        prompt_file_path: Path | None = None

        if parsed_arguments_namespace.prompt_file:
            prompt_file_path = Path(parsed_arguments_namespace.prompt_file).resolve()

        if prompt_file_path is not None and not prompt_file_path.exists():
            logger.error(f"Custom prompt file not found: {prompt_file_path}")
            sys.exit(1)

        if parsed_arguments_namespace.token:
            save_authentication_token(parsed_arguments_namespace.token)

        is_force_update: bool = False
        if parsed_arguments_namespace.command == "run":
            is_force_update = parsed_arguments_namespace.force_update

        execute_initialization_workflow(
            experiment_name_string=parsed_arguments_namespace.experiment,
            model_archetype_string=parsed_arguments_namespace.model,
            publish_boolean_flag=parsed_arguments_namespace.publish,
            target_directory_path=target_directory_path,
            watch_boolean_flag=parsed_arguments_namespace.watch,
            slurm_boolean_flag=parsed_arguments_namespace.slurm,
            include_pattern_string=parsed_arguments_namespace.include,
            exclude_pattern_string=parsed_arguments_namespace.exclude,
            is_force_update_boolean=is_force_update,
            prompt_file_path=prompt_file_path,
            model_provider_string=parsed_arguments_namespace.provider,
            target_document_string=parsed_arguments_namespace.template,
        )
        return


if __name__ == "__main__":
    main()

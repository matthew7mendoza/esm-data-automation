"""
Main command line interface entrypoint for esm-tracker.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Final

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from esm_tracker.publisher import publish_to_api, write_yaml_locally
from esm_tracker.spider import crawl_directory

logger: Final[logging.Logger] = logging.getLogger("esm_tracker")


def configure_logging() -> None:
    """Sets up highly descriptive console logging for interns and scientists."""
    # We configure the root logger to catch output from our modules
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def run_tracking_pipeline(
    experiment_name: str,
    model_archetype: str,
    publish: bool,
    target_directory: Path,
    api_endpoint: str,
) -> None:
    """
    Coordinates the crawling and publishing workflow using flat logic.
    """
    logger.info(
        f"Initializing tracking for experiment: {experiment_name} | "
        f"Model: {model_archetype}"
    )

    extracted_datasets = crawl_directory(target_directory=target_directory)

    if not extracted_datasets:
        logger.warning("No NetCDF data found. Writing empty project summary.")

    project_summary_payload: dict[str, Any] = {
        "experiment_name": experiment_name,
        "model_archetype": model_archetype,
        "datasets": extracted_datasets,
    }

    output_yaml_path = target_directory / "project_summary.yaml"

    if publish:
        logger.info(f"Publish flag detected. Will attempt to send to {api_endpoint}")

        publish_success = publish_to_api(
            api_endpoint=api_endpoint,
            payload_data=project_summary_payload,
            output_path=output_yaml_path,
        )

        if publish_success:
            logger.info("Publishing workflow complete. Check the web dashboard!")
        else:
            logger.error("Publishing workflow failed. Local file is still available.")
    else:
        logger.info("No publish flag detected. Saving local YAML only.")
        write_yaml_locally(
            output_path=output_yaml_path, payload=project_summary_payload
        )
        logger.info(f"Spider finished. File generated at {output_yaml_path}")


class NetCDFHandler(FileSystemEventHandler):
    """Watches for newly created NetCDF files to trigger the pipeline."""

    def __init__(self, pipeline_kwargs: dict[str, Any]) -> None:
        super().__init__()
        self.pipeline_kwargs = pipeline_kwargs

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and str(event.src_path).endswith(".nc"):
            logger.info(f"New NetCDF file detected: {event.src_path!s}")
            run_tracking_pipeline(**self.pipeline_kwargs)


def execute_initialization(
    experiment_name: str,
    model_archetype: str,
    publish: bool,
    target_directory: Path,
    watch: bool,
) -> None:
    """Sets up the environment and determines single-run vs daemon mode."""
    api_endpoint = os.environ.get(
        "ESM_TRACKER_API_URL", "http://localhost:8000/api/generate"
    )

    pipeline_kwargs: dict[str, Any] = {
        "experiment_name": experiment_name,
        "model_archetype": model_archetype,
        "publish": publish,
        "target_directory": target_directory,
        "api_endpoint": api_endpoint,
    }

    run_tracking_pipeline(**pipeline_kwargs)

    if watch:
        logger.info("Watch mode enabled. Daemon sleeping and waiting for new files...")

        event_handler = NetCDFHandler(pipeline_kwargs=pipeline_kwargs)
        observer = Observer()
        observer.schedule(event_handler, str(target_directory), recursive=True)
        observer.start()

        logger.info(f"Observer successfully scheduled on {target_directory}.")

        try:
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Watch interrupted by user. Shutting down daemon.")
            observer.stop()

        observer.join()
        logger.info("Daemon shutdown complete. Goodbye.")


def main() -> None:
    """Entry point for the esm-tracker CLI."""
    configure_logging()

    argument_parser = argparse.ArgumentParser(
        description=(
            "ESM Data Automation Tracker - Spiders NetCDF files to extract metadata."
        )
    )

    subparsers = argument_parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Initialize a new experiment tracking sequence."
    )
    init_parser.add_argument(
        "--experiment", required=True, type=str, help="Name of the experiment to track."
    )
    init_parser.add_argument(
        "--model", required=True, type=str, help="Model archetype (e.g. 'GFDL SPEAR')."
    )
    init_parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish the generated YAML straight to the API.",
    )
    init_parser.add_argument(
        "--watch",
        action="store_true",
        help="Run as a daemon and automatically refresh when new files appear.",
    )
    init_parser.add_argument(
        "--directory",
        type=str,
        default=".",
        help="Target directory to crawl. Defaults to current working directory.",
    )

    parsed_arguments = argument_parser.parse_args()

    if parsed_arguments.command == "init":
        target_path = Path(parsed_arguments.directory).resolve()
        execute_initialization(
            experiment_name=parsed_arguments.experiment,
            model_archetype=parsed_arguments.model,
            publish=parsed_arguments.publish,
            target_directory=target_path,
            watch=parsed_arguments.watch,
        )


if __name__ == "__main__":
    main()

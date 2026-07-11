"""
Spider module for crawling directories and extracting NetCDF metadata.
"""

import logging
from pathlib import Path
from typing import Any, Final

import xarray

logger: Final[logging.Logger] = logging.getLogger(__name__)


def scan_netcdf_file(file_path: Path) -> dict[str, Any] | None:  # noqa: C901
    """
    Attempts to lazily read a single NetCDF file and extract its core metadata.
    """
    logger.debug(f"Attempting to scan file: {file_path}")

    dataset = None
    try:
        # We explicitly use the netcdf4 engine and ensure lazy loading
        dataset = xarray.open_dataset(file_path, engine="netcdf4")
    except (FileNotFoundError, PermissionError) as file_access_error:
        logger.warning(f"OS error accessing {file_path}: {file_access_error}")
        return None
    except ValueError as value_error:
        logger.warning(
            f"Value error parsing {file_path} (possibly unsupported format): "
            f"{value_error}"
        )
        return None

    except OSError as os_error:
        # netCDF4 raises OSError for corrupted or non-netCDF files
        logger.warning(f"Corrupted or invalid NetCDF file {file_path}: {os_error}")
        return None

    extracted_metadata: dict[str, Any] = {}

    try:
        logger.debug(
            f"File {file_path.name} opened successfully. Extracting physical metadata."
        )

        extracted_metadata["file_name"] = file_path.name
        extracted_metadata["file_size_bytes"] = file_path.stat().st_size

        # Extract variables, ignoring coordinate dimensions where possible
        data_variables: list[str] = list(dataset.data_vars.keys())
        extracted_metadata["variables"] = data_variables

        dimensions: dict[str, int] = dict(dataset.dims)
        extracted_metadata["dimensions"] = dimensions

        global_attributes: dict[str, Any] = dict(dataset.attrs)
        extracted_metadata["global_attributes"] = global_attributes

        logger.info(
            f"Successfully extracted metadata from {file_path.name} "
            f"with {len(data_variables)} variables."
        )

    except KeyError as key_error:
        logger.warning(f"Missing expected keys in dataset {file_path}: {key_error}")

    finally:
        if dataset is not None:
            dataset.close()
            logger.debug(f"Closed dataset for {file_path} to prevent memory leaks.")

    return extracted_metadata


def crawl_directory(target_directory: Path) -> list[dict[str, Any]]:
    """
    Recursively finds all .nc files and extracts metadata using
    deterministic flat logic.
    """
    logger.info(f"Starting directory crawl at root: {target_directory}")

    if not target_directory.exists():
        logger.error(f"Target directory does not exist: {target_directory}")
        return []

    if not target_directory.is_dir():
        logger.error(f"Target path is not a directory: {target_directory}")
        return []

    found_metadata_list: list[dict[str, Any]] = []

    # Use pathlib to yield files lazily without building massive memory lists
    netcdf_files_generator = target_directory.rglob("*.nc")

    for netcdf_file in netcdf_files_generator:
        logger.debug(f"Found NetCDF file target: {netcdf_file}")
        file_metadata = scan_netcdf_file(file_path=netcdf_file)

        if file_metadata is None:
            continue

        found_metadata_list.append(file_metadata)

    total_files_processed = len(found_metadata_list)
    logger.info(
        "Directory crawl completed. "
        f"Successfully processed {total_files_processed} valid NetCDF files."
    )

    return found_metadata_list

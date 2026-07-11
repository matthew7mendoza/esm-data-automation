"""
Pytest configuration and programmatic dummy data generation.
"""

import logging
from pathlib import Path
from typing import Final

import numpy
import pytest
import xarray

logger: Final[logging.Logger] = logging.getLogger(__name__)


@pytest.fixture
def dummy_netcdf_file_path(tmp_path: Path) -> Path:
    """Generates a strictly deterministic NetCDF file for scanning."""
    logger.info("Initializing dummy NetCDF dataset generation.")

    try:
        latitude_array = numpy.linspace(-90, 90, 10)
        longitude_array = numpy.linspace(-180, 180, 20)
        temperature_array = numpy.random.rand(10, 20)

        mock_dataset = xarray.Dataset(
            data_vars={
                "surface_temperature": (
                    ["latitude", "longitude"],
                    temperature_array,
                )
            },
            coords={"latitude": latitude_array, "longitude": longitude_array},
            attrs={"history": "Created programmatically for automated testing"},
        )
    except Exception as data_generation_error:
        logger.error(
            f"Failed to assemble dummy dataset in memory: {data_generation_error}"
        )
        raise

    target_file_path: Path = tmp_path / "mock_ocean_data.nc"

    try:
        mock_dataset.to_netcdf(target_file_path)
        logger.info(f"Successfully wrote dummy NetCDF file to: {target_file_path}")
    except OSError as disk_write_error:
        logger.error(f"Failed to write mock NetCDF file to disk: {disk_write_error}")
        raise

    return target_file_path

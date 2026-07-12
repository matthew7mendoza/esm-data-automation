"""
Automated unit tests for the deterministic scanning operations.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock, patch

from esm_tracker.scanner import (
    FileMetadata,
    JsonCacheBackend,
    SqliteCacheBackend,
    _initialize_cache_backend,
    _is_file_offline,
    _open_dataset,
    _parse_dataset_metadata,
    _safe_open_dataset,
    determine_file_requires_scanning,
    get_file_modification_time,
    process_files_in_parallel,
    scan_data_file,
    scan_directory,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


def test_determine_file_requires_scanning_includes_correctly() -> None:
    """Validates that regex inclusion logic correctly matches target files."""
    logger.info(
        "Executing test: test_determine_file_requires_scanning_includes_correctly"
    )

    dummy_file_path: Path = Path("/fake/directory/ocean_monthly.nc")

    inclusion_boolean: bool = determine_file_requires_scanning(
        data_file_path=dummy_file_path,
        include_pattern_string="*.nc",
        exclude_pattern_string="",
    )

    if not inclusion_boolean:
        logger.error(f"Expected {dummy_file_path} to be included, but it was rejected.")

    assert inclusion_boolean is True


def test_determine_file_requires_scanning_excludes_correctly() -> None:
    """Validates that regex exclusion logic correctly ignores restart files."""
    logger.info(
        "Executing test: test_determine_file_requires_scanning_excludes_correctly"
    )

    dummy_file_path: Path = Path("/fake/directory/ocean_monthly_restart.nc")

    inclusion_boolean: bool = determine_file_requires_scanning(
        data_file_path=dummy_file_path,
        include_pattern_string="*.nc",
        exclude_pattern_string="*restart*",
    )

    if inclusion_boolean:
        logger.error(f"Expected {dummy_file_path} to be excluded, but it was included.")

    assert inclusion_boolean is False


def test_scan_directory_extracts_metadata_flawlessly(
    dummy_netcdf_file_path: Path,
) -> None:
    """
    Ensures deterministic math extraction from binary files is completely accurate.
    """
    logger.info("Executing test: test_scan_directory_extracts_metadata_flawlessly")

    target_directory_path: Path = dummy_netcdf_file_path.parent

    extracted_metadata_list: list[FileMetadata] = scan_directory(
        target_directory_path=target_directory_path,
        include_pattern_string="*.nc",
        exclude_pattern_string="*restart*",
    )

    if not extracted_metadata_list:
        logger.error("Scanner failed to find the dummy NetCDF file.")

    assert len(extracted_metadata_list) == 1

    extracted_file_metadata: FileMetadata = extracted_metadata_list[0]

    if extracted_file_metadata["file_name"] != "mock_ocean_data.nc":
        logger.error(
            f"Incorrect file name extracted: {extracted_file_metadata['file_name']}"
        )

    assert extracted_file_metadata["file_name"] == "mock_ocean_data.nc"
    assert "surface_temperature" in extracted_file_metadata["variables"]
    assert extracted_file_metadata["dimensions"]["latitude"] == 10
    assert extracted_file_metadata["dimensions"]["longitude"] == 20
    assert (
        extracted_file_metadata["global_attributes"]["history"]
        == "Created programmatically for automated testing"
    )


@patch("esm_tracker.scanner._is_file_offline", return_value=True)
def test_scan_data_file_offline(
    _mock_offline_check: MagicMock, dummy_netcdf_file_path: Path
) -> None:
    """Validates resilience when encountering tape-migrated offline files."""
    extracted_metadata: FileMetadata | None = scan_data_file(
        file_path=dummy_netcdf_file_path
    )

    if extracted_metadata is None:
        logger.error(
            "Scanner returned None instead of error metadata for offline file."
        )

    assert extracted_metadata is not None
    assert extracted_metadata["status"] == "tape_migrated"
    assert extracted_metadata["file_name"] == "mock_ocean_data.nc"


@patch("esm_tracker.scanner._open_dataset")
def test_scan_data_file_permission_error(
    mock_open_dataset: MagicMock, dummy_netcdf_file_path: Path
) -> None:
    """Validates resilience when encountering permission errors."""
    mock_open_dataset.side_effect = PermissionError("Access Denied")

    extracted_metadata: FileMetadata | None = scan_data_file(
        file_path=dummy_netcdf_file_path
    )

    if extracted_metadata is None:
        logger.error(
            "Scanner returned None instead of error metadata for permission denied."
        )

    assert extracted_metadata is not None
    assert extracted_metadata["status"] == "permission_denied"


def test_sqlite_cache_backend(tmp_path: Path) -> None:
    """Validates the heavy-duty SQLite incremental cache."""
    database_file_path: Path = tmp_path / ".esm-cache.db"
    cache_backend_object = SqliteCacheBackend(database_file_path=database_file_path)

    dummy_metadata: FileMetadata = {
        "file_name": "test.nc",
        "file_size_bytes": 100,
        "status": "ok",
        "variables": [],
        "dimensions": {},
        "global_attributes": {},
    }

    cache_backend_object.update_cache_entry(
        file_path_string="/fake/path/test.nc",
        modification_time=12345.0,
        metadata=dummy_metadata,
    )

    retrieved_metadata: FileMetadata | None = cache_backend_object.get_cached_metadata(
        file_path_string="/fake/path/test.nc", current_modification_time=12345.0
    )

    if retrieved_metadata is None:
        logger.error("SQLite cache failed to return stored metadata on hit.")

    assert retrieved_metadata is not None
    assert retrieved_metadata["file_name"] == "test.nc"

    missed_metadata: FileMetadata | None = cache_backend_object.get_cached_metadata(
        file_path_string="/fake/path/test.nc", current_modification_time=99999.0
    )

    if missed_metadata is not None:
        logger.error("SQLite cache incorrectly returned metadata on time mismatch.")

    assert missed_metadata is None
    cache_backend_object.finalize_cache()


def test_process_files_in_parallel_empty() -> None:
    """Validates the parallel executor handles empty lists gracefully."""
    results_list = process_files_in_parallel([])
    assert not results_list


def test_json_cache_backend(tmp_path: Path) -> None:
    cache_path = tmp_path / ".esm-cache.json"
    backend = JsonCacheBackend(cache_path)
    backend.update_cache_entry(
        "test.nc",
        1.0,
        {
            "file_name": "test.nc",
            "file_size_bytes": 0,
            "status": "ok",
            "variables": [],
            "dimensions": {},
            "global_attributes": {},
        },
    )
    backend.finalize_cache()

    backend2 = JsonCacheBackend(cache_path)
    assert backend2.get_cached_metadata("test.nc", 1.0) is not None
    assert backend2.get_cached_metadata("test.nc", 2.0) is None


def test_json_cache_backend_corrupt(tmp_path: Path) -> None:
    cache_path = tmp_path / ".esm-cache.json"
    cache_path.write_text("{invalid")
    backend = JsonCacheBackend(cache_path)
    assert not backend.cache_data_dictionary


def test_sqlite_cache_backend_corrupt_json(tmp_path: Path) -> None:
    db_path = tmp_path / ".esm-cache.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE file_cache (file_path TEXT PRIMARY KEY, "
        "modification_time REAL, metadata_json TEXT)"
    )
    conn.execute("INSERT INTO file_cache VALUES ('test.nc', 1.0, '{invalid')")
    conn.commit()
    backend = SqliteCacheBackend(db_path)
    assert backend.get_cached_metadata("test.nc", 1.0) is None


@patch("esm_tracker.scanner.Path.stat")
def test_get_file_modification_time_os_error(mock_stat: MagicMock) -> None:
    mock_stat.side_effect = OSError("Err")
    assert get_file_modification_time(Path("test.nc")) == 0.0


@patch("esm_tracker.scanner.Path.stat")
def test_is_file_offline_os_error(mock_stat: MagicMock) -> None:
    mock_stat.side_effect = OSError("Err")
    assert _is_file_offline(Path("test.nc")) is False


def test_is_file_offline_zarr_no_metadata(tmp_path: Path) -> None:
    zarr_path = tmp_path / "test.zarr"
    assert _is_file_offline(zarr_path) is False


def test_open_dataset_invalid_suffix() -> None:
    assert _open_dataset(Path("test.txt")) is None


def test_safe_open_dataset_general_error() -> None:
    with patch("esm_tracker.scanner._open_dataset", side_effect=Exception("Err")):
        res = _safe_open_dataset(Path("test.nc"))
        assert res is not None
        assert res["status"] == "corrupted"


def test_parse_dataset_metadata_keyerror() -> None:
    mock_ds = MagicMock()
    mock_ds.attrs = MagicMock()
    with patch(
        "esm_tracker.scanner.extract_metadata_from_dataset", side_effect=KeyError("Key")
    ):
        assert _parse_dataset_metadata(mock_ds, Path("test.nc")) is None


def test_scan_data_file_returns_error_metadata() -> None:
    with patch(
        "esm_tracker.scanner._safe_open_dataset", return_value={"status": "corrupted"}
    ):
        res = scan_data_file(Path("test.nc"))
        assert res is not None
        assert res["status"] == "corrupted"


def test_migrate_json_to_sqlite(tmp_path: Path) -> None:
    json_cache = tmp_path / ".esm-cache.json"
    json_cache.write_text(
        '{"test.nc": {"modification_time": 1.0, "metadata": {"file_name": "test.nc"}}}'
    )

    # 50,001 files to trigger migration
    dummy_files = [Path(f"file_{i}.nc") for i in range(50001)]
    backend = _initialize_cache_backend(tmp_path, dummy_files)
    assert isinstance(backend, SqliteCacheBackend)
    assert backend.get_cached_metadata("test.nc", 1.0) is not None


def test_scan_directory_invalid() -> None:
    assert scan_directory(Path("/invalid/path/that/does/not/exist")) == []


@patch("esm_tracker.scanner.process_files_in_parallel")
def test_scan_directory_full_flow(mock_parallel: MagicMock, tmp_path: Path) -> None:
    nc_file = tmp_path / "test.nc"
    nc_file.write_text("data")
    mock_parallel.return_value = [{"file_name": "test.nc"}]
    res = scan_directory(tmp_path)
    assert len(res) == 1


def test_scan_data_file_success_main_process(dummy_netcdf_file_path: Path) -> None:
    res = scan_data_file(dummy_netcdf_file_path)
    assert res is not None
    assert res["file_name"] == "mock_ocean_data.nc"
    assert "surface_temperature" in res["variables"]

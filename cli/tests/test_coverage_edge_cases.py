"""
Targeted tests for specific edge cases in the CLI, publisher, and scanner modules.
"""

import logging
import runpy
import sqlite3
import sys
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock, patch

import pytest
import xarray
from esm_tracker.publisher import publish_to_api
from esm_tracker.scanner import (
    FileMetadata,
    JsonCacheBackend,
    SqliteCacheBackend,
    _initialize_cache_backend,
    _is_file_offline,
    _open_dataset,
    _process_file_for_scanning,
    _update_cache_with_results,
    _validate_target_directory,
    determine_file_requires_scanning,
    scan_data_file,
    scan_directory,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


def test_publisher_prompt_file_read_error(tmp_path: Path) -> None:
    """Tests the OSError exception when reading a custom prompt file."""
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text("data")
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("data")
    config = tmp_path / ".esm-tracker-config"
    config.write_text('{"api_token": "abc"}')

    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
        patch(
            "esm_tracker.publisher.Path.read_bytes",
            side_effect=[b"yaml data", OSError("Prompt err")],
        ),
        patch("esm_tracker.publisher.requests.post") as mock_post,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"task_id": "123"}
        mock_post.return_value = mock_response

        publish_to_api("http", "http", {}, yaml_path, prompt_path)


def test_publisher_config_os_error(tmp_path: Path) -> None:
    """Tests OSError when reading config."""
    yaml_path = tmp_path / "test.yaml"
    config = tmp_path / ".esm-tracker-config"
    config.write_text("{}")
    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
        patch("builtins.open", side_effect=OSError("OS Err")),
    ):
        assert publish_to_api("http", "http", {}, yaml_path) is False


def test_publisher_config_json_decode_error(tmp_path: Path) -> None:
    """Tests the JSON decode error inside the config loader."""
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text("data")
    config = tmp_path / ".esm-tracker-config"
    config.write_text("{invalid")

    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
    ):
        res = publish_to_api("http", "http", {}, yaml_path)
        assert res is False


def test_publisher_prompt_file_happy_path(tmp_path: Path) -> None:
    """Tests the happy path for the prompt file loading."""
    yaml_path = tmp_path / "test.yaml"
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("prompt content")
    config = tmp_path / ".esm-tracker-config"
    config.write_text('{"api_token": "abc"}')

    with (
        patch("esm_tracker.publisher.Path.home", return_value=tmp_path),
        patch("esm_tracker.publisher.requests.post") as mock_post,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"task_id": "123"}
        mock_post.return_value = mock_response

        publish_to_api("http", "http", {}, yaml_path, prompt_path)


def test_publisher_config_os_error_exact(tmp_path: Path) -> None:
    """Tests OSError explicitly when calling open on the config file."""
    yaml_path = tmp_path / "test.yaml"
    config = tmp_path / ".esm-tracker-config"
    config.mkdir()
    with patch("esm_tracker.publisher.Path.home", return_value=tmp_path):
        assert publish_to_api("http", "http", {}, yaml_path) is False


def test_scanner_json_finalize_os_error(tmp_path: Path) -> None:
    """Tests OSError during JSON cache finalize."""
    cache = tmp_path / ".esm-cache.json"
    backend = JsonCacheBackend(cache)
    with patch("esm_tracker.scanner.Path.open", side_effect=OSError("OS Err")):
        backend.finalize_cache()


def test_scanner_sqlite_fetch_none(tmp_path: Path) -> None:
    """Tests the none return on sqlite fetch."""
    db = tmp_path / ".esm-cache.db"
    backend = SqliteCacheBackend(db)
    assert backend.get_cached_metadata("nonexistent", 1.0) is None


def test_scanner_sqlite_finalize_error(tmp_path: Path) -> None:
    """Tests sqlite3.Error on database finalize."""
    db = tmp_path / ".esm-cache.db"
    backend = SqliteCacheBackend(db)
    mock_conn = MagicMock()
    mock_conn.commit.side_effect = sqlite3.Error("DB Err")
    backend.database_connection = mock_conn
    backend.finalize_cache()


def test_scanner_is_file_offline_zarr(tmp_path: Path) -> None:
    """Tests zarr offline check returning False when no metadata."""
    zarr_dir = tmp_path / "data.zarr"
    zarr_dir.mkdir()
    (zarr_dir / ".zmetadata").write_text("{}")
    assert _is_file_offline(zarr_dir) is False


def test_scanner_open_dataset_zarr() -> None:
    """Tests the open_dataset for zarr engine."""
    with patch("esm_tracker.scanner.xarray.open_dataset") as mock_open:
        mock_open.return_value = "zarr_mock"
        assert _open_dataset(Path("test.zarr")) == "zarr_mock"


def test_scanner_scan_data_file_unknown_format() -> None:
    """Tests scan_data_file dataset_or_error is None branch."""
    with patch("esm_tracker.scanner._safe_open_dataset", return_value=None):
        assert scan_data_file(Path("test.txt")) is None


def test_scanner_scan_data_file_parse_error() -> None:
    """Tests scan_data_file extracted_metadata is None branch."""
    with (
        patch("esm_tracker.scanner._safe_open_dataset", return_value=xarray.Dataset()),
        patch("esm_tracker.scanner._parse_dataset_metadata", return_value=None),
    ):
        res = scan_data_file(Path("test.nc"))
        assert res is not None
        assert res["status"] == "corrupted"


def test_scanner_determine_file_requires_scanning_exclude() -> None:
    """Tests exclude pattern logging."""
    assert (
        determine_file_requires_scanning(Path("restart.nc"), "*", "*restart*") is False
    )
    assert determine_file_requires_scanning(Path("test.txt"), "*.nc", "") is False


def test_scanner_process_file_for_scanning_not_required(tmp_path: Path) -> None:
    """Tests requires_scanning_boolean False branch."""
    backend = JsonCacheBackend(tmp_path / "cache.json")
    req, meta = _process_file_for_scanning(
        Path("restart.nc"), "*", "*restart*", backend
    )
    assert req is False
    assert meta is None


def test_scanner_process_file_for_scanning_cache_hit(tmp_path: Path) -> None:
    """Tests cached_metadata is not None branch."""
    backend = JsonCacheBackend(tmp_path / "cache.json")
    backend.update_cache_entry("test.nc", 1.0, {"file_name": "test.nc"})  # type: ignore
    with patch("esm_tracker.scanner.get_file_modification_time", return_value=1.0):
        req, meta = _process_file_for_scanning(Path("test.nc"), "*.nc", "", backend)
        assert req is False
        assert meta is not None


def test_scanner_validate_target_directory_errors(tmp_path: Path) -> None:
    """Tests directory validation errors."""
    assert _validate_target_directory(Path("/does/not/exist")) is False
    file_path = tmp_path / "file.txt"
    file_path.write_text("txt")
    assert _validate_target_directory(file_path) is False


def test_scanner_update_cache_with_results_none(tmp_path: Path) -> None:
    """Tests scan_result_object is None continue branch."""
    backend = JsonCacheBackend(tmp_path / "cache.json")
    found_metadata_list: list[FileMetadata] = []
    _update_cache_with_results([Path("test.nc")], [None], backend, found_metadata_list)
    assert not found_metadata_list


def test_scanner_initialize_cache_backend_massive(tmp_path: Path) -> None:
    """Tests massive dataset threshold JSON initialization."""
    dummy_files = [Path(f"{i}.nc") for i in range(50001)]
    sqlite = tmp_path / ".esm-cache.db"
    if sqlite.exists():
        sqlite.unlink()
    json_path = tmp_path / ".esm-cache.json"
    json_path.write_text(
        '{"test": {"modification_time": 1.0, "metadata": {"file_name": "test.nc"}}}'
    )
    backend = _initialize_cache_backend(tmp_path, dummy_files)
    assert isinstance(backend, SqliteCacheBackend)


def test_scanner_initialize_cache_backend_small(tmp_path: Path) -> None:
    """Tests small dataset threshold JSON."""
    json_path = tmp_path / ".esm-cache.json"
    sqlite = tmp_path / ".esm-cache.db"
    if sqlite.exists():
        sqlite.unlink()
    if json_path.exists():
        json_path.unlink()
    backend = _initialize_cache_backend(tmp_path, [Path("test.nc")])
    assert isinstance(backend, JsonCacheBackend)


def test_scanner_initialize_cache_backend_existing_sqlite(tmp_path: Path) -> None:
    """Tests that an existing SQLite DB is directly used."""
    sqlite = tmp_path / ".esm-cache.db"
    sqlite.touch()
    backend = _initialize_cache_backend(tmp_path, [])
    assert isinstance(backend, SqliteCacheBackend)


def test_scanner_scan_directory_cache_hit(tmp_path: Path) -> None:
    """Tests scan_directory cached_metadata branch."""
    nc = tmp_path / "test.nc"
    nc.write_text("data")
    backend_path = tmp_path / ".esm-cache.json"
    backend = JsonCacheBackend(backend_path)
    backend.update_cache_entry(str(nc), nc.stat().st_mtime, {"file_name": "test.nc"})  # type: ignore
    backend.finalize_cache()

    res = scan_directory(tmp_path)
    assert len(res) == 1


def test_cli_main_block() -> None:
    """Tests the script execution block."""
    if "esm_tracker.cli" in sys.modules:
        del sys.modules["esm_tracker.cli"]
    with (
        pytest.raises(SystemExit),
        patch.object(sys, "argv", ["esm-tracker", "init"]),
    ):
        runpy.run_module("esm_tracker.cli", run_name="__main__")

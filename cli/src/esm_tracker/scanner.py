"""
Scanner module for extracting metadata from NetCDF and Zarr files.
"""

import concurrent.futures
import contextlib
import fnmatch
import itertools
import json
import logging
import multiprocessing
import sqlite3
from pathlib import Path
from typing import Final, Protocol, TypedDict

import xarray

logger: Final[logging.Logger] = logging.getLogger(__name__)

MASSIVE_FILE_COUNT_THRESHOLD: Final[int] = 50_000


class FileMetadata(TypedDict):
    """Strongly typed structure for extracted dataset metadata."""

    file_name: str
    file_size_bytes: int
    status: str
    variables: list[str]
    dimensions: dict[str, int]
    global_attributes: dict[str, object]


class CacheEntry(TypedDict):
    """Strongly typed structure for the legacy incremental cache entries."""

    modification_time: float
    metadata: FileMetadata


class CacheBackendProtocol(Protocol):
    """Protocol defining a unified interface for JSON and SQLite caches."""

    def get_cached_metadata(
        self, file_path_string: str, current_modification_time: float
    ) -> FileMetadata | None: ...

    def update_cache_entry(
        self, file_path_string: str, modification_time: float, metadata: FileMetadata
    ) -> None: ...

    def finalize_cache(self) -> None: ...


class JsonCacheBackend:
    """Standard lightweight cache backend writing directly to JSON."""

    def __init__(self, cache_file_path: Path) -> None:
        self.cache_file_path: Path = cache_file_path
        self.cache_data_dictionary: dict[str, CacheEntry] = {}
        self._load_cache_from_disk()

    def _load_cache_from_disk(self) -> None:
        if not self.cache_file_path.exists():
            logger.info(f"No existing cache found at {self.cache_file_path}.")
            return

        try:
            with self.cache_file_path.open("r", encoding="utf-8") as file_handle:
                self.cache_data_dictionary = json.load(file_handle)
                logger.info(
                    f"Successfully loaded JSON cache from {self.cache_file_path}."
                )
        except (json.JSONDecodeError, OSError) as cache_read_error:
            logger.error(
                f"Failed to read JSON cache at {self.cache_file_path}: "
                f"{cache_read_error}"
            )
            self.cache_data_dictionary = {}

    def get_cached_metadata(
        self, file_path_string: str, current_modification_time: float
    ) -> FileMetadata | None:
        cached_entry: CacheEntry | None = self.cache_data_dictionary.get(
            file_path_string
        )
        if cached_entry is None:
            return None

        if cached_entry.get("modification_time") != current_modification_time:
            return None

        return cached_entry["metadata"]

    def update_cache_entry(
        self, file_path_string: str, modification_time: float, metadata: FileMetadata
    ) -> None:
        self.cache_data_dictionary[file_path_string] = {
            "modification_time": modification_time,
            "metadata": metadata,
        }

    def finalize_cache(self) -> None:
        try:
            with self.cache_file_path.open("w", encoding="utf-8") as file_handle:
                json.dump(self.cache_data_dictionary, file_handle, indent=4)
            logger.info(f"Successfully saved JSON cache to {self.cache_file_path}.")
        except (OSError, TypeError) as cache_save_error:
            logger.error(
                f"Failed to save JSON cache to {self.cache_file_path}: "
                f"{cache_save_error}"
            )


class SqliteCacheBackend:
    """Heavy-duty cache backend scaling to millions with zero memory bloat."""

    def __init__(self, database_file_path: Path) -> None:
        self.database_file_path: Path = database_file_path
        self.database_connection: sqlite3.Connection = sqlite3.connect(
            str(database_file_path)
        )
        self._initialize_database_schema()

    def _initialize_database_schema(self) -> None:
        schema_query_string: str = (
            "CREATE TABLE IF NOT EXISTS file_cache ("
            "file_path TEXT PRIMARY KEY, "
            "modification_time REAL, "
            "metadata_json TEXT)"
        )
        with contextlib.closing(self.database_connection.cursor()) as cursor_object:
            cursor_object.execute(schema_query_string)
        self.database_connection.commit()

    def get_cached_metadata(
        self, file_path_string: str, current_modification_time: float
    ) -> FileMetadata | None:
        query_string: str = (
            "SELECT modification_time, metadata_json FROM file_cache "
            "WHERE file_path = ?"
        )
        with contextlib.closing(self.database_connection.cursor()) as cursor_object:
            cursor_object.execute(query_string, (file_path_string,))
            fetched_row: tuple[float, str] | None = cursor_object.fetchone()

        if fetched_row is None:
            return None

        cached_modification_time_float: float = fetched_row[0]
        if cached_modification_time_float != current_modification_time:
            return None

        try:
            parsed_metadata_dictionary: FileMetadata = json.loads(fetched_row[1])
            return parsed_metadata_dictionary
        except json.JSONDecodeError as decode_error:
            logger.warning(
                f"Corrupted cache JSON for {file_path_string}: {decode_error}"
            )
            return None

    def update_cache_entry(
        self, file_path_string: str, modification_time: float, metadata: FileMetadata
    ) -> None:
        query_string: str = (
            "INSERT OR REPLACE INTO file_cache "
            "(file_path, modification_time, metadata_json) "
            "VALUES (?, ?, ?)"
        )
        metadata_json_string: str = json.dumps(metadata)
        with contextlib.closing(self.database_connection.cursor()) as cursor_object:
            cursor_object.execute(
                query_string,
                (file_path_string, modification_time, metadata_json_string),
            )

    def finalize_cache(self) -> None:
        try:
            self.database_connection.commit()
            self.database_connection.close()
            logger.info(
                f"Successfully committed SQLite database at {self.database_file_path}"
            )
        except sqlite3.Error as database_error:
            logger.error(
                f"Failed to finalize database {self.database_file_path}: "
                f"{database_error}"
            )


def get_file_modification_time(file_path: Path) -> float:
    """Returns the last modification time of a file, or zero if it fails."""
    try:
        return file_path.stat().st_mtime
    except OSError as os_error:
        logger.warning(f"Could not read modification time for {file_path}: {os_error}")
        return 0.0


def extract_metadata_from_dataset(
    dataset: xarray.Dataset, file_path: Path
) -> FileMetadata:
    """Extracts strictly typed metadata from an open xarray dataset."""
    file_name_string: str = file_path.name
    file_size_integer: int = file_path.stat().st_size

    data_variables_list: list[str] = [str(key) for key in dataset.data_vars]
    dimensions_dictionary: dict[str, int] = {
        str(key): int(value) for key, value in dataset.sizes.items()
    }
    global_attributes_dictionary: dict[str, object] = dict(dataset.attrs)

    extracted_metadata: FileMetadata = {
        "file_name": file_name_string,
        "file_size_bytes": file_size_integer,
        "status": "ok",
        "variables": data_variables_list,
        "dimensions": dimensions_dictionary,
        "global_attributes": global_attributes_dictionary,
    }

    return extracted_metadata


def _is_file_offline(file_path: Path) -> bool:
    """Checks if a file is offline or migrated to tape storage."""
    path_to_check: Path = file_path

    if file_path.suffix == ".zarr":
        metadata_file_path: Path = file_path / ".zmetadata"
        if not metadata_file_path.exists():
            return False
        path_to_check = metadata_file_path

    try:
        file_stat_result = path_to_check.stat()
        return (
            file_stat_result.st_size > 0
            and getattr(file_stat_result, "st_blocks", 1) == 0
        )
    except OSError as os_error:
        logger.warning(f"Could not stat file {path_to_check}: {os_error}")
        return False


def _create_error_metadata(file_path: Path, status_string: str) -> FileMetadata:
    """Helper to create an error FileMetadata entry for resilience tracking."""
    file_size_integer: int = 0
    with contextlib.suppress(OSError):
        file_size_integer = file_path.stat().st_size

    error_metadata: FileMetadata = {
        "file_name": file_path.name,
        "file_size_bytes": file_size_integer,
        "status": status_string,
        "variables": [],
        "dimensions": {},
        "global_attributes": {},
    }
    return error_metadata


def _open_dataset(file_path: Path) -> xarray.Dataset | None:
    """Helper to open NetCDF or Zarr based on suffix."""
    if file_path.suffix == ".nc":
        return xarray.open_dataset(file_path, engine="netcdf4")
    if file_path.suffix == ".zarr":
        return xarray.open_dataset(file_path, engine="zarr")

    logger.debug(f"File {file_path} is neither .nc nor .zarr. Skipping.")
    return None


def _parse_dataset_metadata(
    dataset: xarray.Dataset, file_path: Path
) -> FileMetadata | None:
    try:
        logger.debug(f"File {file_path.name} opened. Extracting physical metadata.")
        extracted_metadata: FileMetadata = extract_metadata_from_dataset(
            dataset=dataset, file_path=file_path
        )
        variable_count_integer: int = len(extracted_metadata["variables"])
        logger.info(
            f"Extracted {variable_count_integer} variables from {file_path.name}."
        )
        return extracted_metadata
    except KeyError as key_error:
        logger.warning(f"Missing keys in dataset {file_path}: {key_error}")
        return None
    finally:
        dataset.close()


def _safe_open_dataset(file_path: Path) -> xarray.Dataset | FileMetadata | None:
    """Safely opens a dataset and catches expected structural errors."""
    try:
        return _open_dataset(file_path=file_path)
    except PermissionError as permission_error:
        logger.warning(f"Permission denied accessing {file_path}: {permission_error}")
        return _create_error_metadata(
            file_path=file_path, status_string="permission_denied"
        )
    except Exception as general_error:
        logger.warning(f"Corrupted or invalid data file {file_path}: {general_error}")
        return _create_error_metadata(file_path=file_path, status_string="corrupted")


def scan_data_file(file_path: Path) -> FileMetadata | None:
    """Lazily reads a NetCDF or Zarr file and extracts metadata, with resilience."""
    logger.debug(f"Attempting to scan file: {file_path}")

    if _is_file_offline(file_path=file_path):
        logger.warning(f"File appears to be offline on tape storage: {file_path}")
        return _create_error_metadata(
            file_path=file_path, status_string="tape_migrated"
        )

    dataset_or_error: xarray.Dataset | FileMetadata | None = _safe_open_dataset(
        file_path=file_path
    )

    if dataset_or_error is None:
        return None

    if not isinstance(dataset_or_error, xarray.Dataset):
        return dataset_or_error

    extracted_metadata: FileMetadata | None = _parse_dataset_metadata(
        dataset=dataset_or_error, file_path=file_path
    )
    if extracted_metadata is None:
        return _create_error_metadata(file_path=file_path, status_string="corrupted")

    return extracted_metadata


def process_files_in_parallel(
    files_to_scan_list: list[Path],
) -> list[FileMetadata | None]:
    """Uses a process pool to scan multiple files simultaneously across CPU cores."""
    if not files_to_scan_list:
        logger.info("No new files require parallel scanning.")
        return []

    logger.info(f"Initiating parallel scan for {len(files_to_scan_list)} files.")

    process_context = multiprocessing.get_context("spawn")

    with concurrent.futures.ProcessPoolExecutor(
        mp_context=process_context
    ) as process_executor:
        parallel_results_iterator = process_executor.map(
            scan_data_file, files_to_scan_list
        )
        parallel_results_list: list[FileMetadata | None] = list(
            parallel_results_iterator
        )

    logger.info("Parallel scanning completely finished.")
    return parallel_results_list


def determine_file_requires_scanning(
    data_file_path: Path, include_pattern_string: str, exclude_pattern_string: str
) -> bool:
    """Evaluates glob patterns to determine if a file should be scanned."""
    file_name_string: str = data_file_path.name

    if not fnmatch.fnmatch(file_name_string, include_pattern_string):
        logger.debug(f"File {file_name_string} skipped (no match).")
        return False

    if exclude_pattern_string and fnmatch.fnmatch(
        file_name_string, exclude_pattern_string
    ):
        logger.debug(
            f"File {file_name_string} skipped because it matches exclude pattern."
        )
        return False

    return True


def _process_file_for_scanning(
    data_file_path: Path,
    include_pattern_string: str,
    exclude_pattern_string: str,
    cache_backend_object: CacheBackendProtocol,
) -> tuple[bool, FileMetadata | None]:
    """Determines if a file needs scanning or can be loaded from cache."""
    requires_scanning_boolean: bool = determine_file_requires_scanning(
        data_file_path=data_file_path,
        include_pattern_string=include_pattern_string,
        exclude_pattern_string=exclude_pattern_string,
    )
    if not requires_scanning_boolean:
        return False, None

    file_path_string: str = str(data_file_path)
    current_modification_time_float: float = get_file_modification_time(
        file_path=data_file_path
    )

    cached_metadata: FileMetadata | None = cache_backend_object.get_cached_metadata(
        file_path_string=file_path_string,
        current_modification_time=current_modification_time_float,
    )

    if cached_metadata is not None:
        logger.debug(f"Cache hit for {file_path_string}. Skipping re-scan.")
        return False, cached_metadata

    logger.debug(f"Cache miss for {file_path_string}. Queuing for parallel scan.")
    return True, None


def _validate_target_directory(target_directory_path: Path) -> bool:
    if not target_directory_path.exists():
        logger.error(f"Path does not exist: {target_directory_path}")
        return False
    if not target_directory_path.is_dir():
        logger.error(f"Path is not a valid directory: {target_directory_path}")
        return False
    return True


def _update_cache_with_results(
    files_to_scan_list: list[Path],
    parallel_results_list: list[FileMetadata | None],
    cache_backend_object: CacheBackendProtocol,
    found_metadata_list: list[FileMetadata],
) -> None:
    """Updates the cache dictionary and appends valid results to found metadata."""
    for file_path_object, scan_result_object in zip(
        files_to_scan_list, parallel_results_list, strict=False
    ):
        if scan_result_object is None:
            continue

        file_path_string: str = str(file_path_object)
        current_modification_time_float: float = get_file_modification_time(
            file_path=file_path_object
        )

        cache_backend_object.update_cache_entry(
            file_path_string=file_path_string,
            modification_time=current_modification_time_float,
            metadata=scan_result_object,
        )
        found_metadata_list.append(scan_result_object)


def _migrate_json_to_sqlite(json_cache_path: Path, sqlite_cache_path: Path) -> None:
    """Migrates legacy JSON cache into the SQLite backend."""
    logger.info("Migrating JSON cache to SQLite backend due to massive dataset size.")
    json_backend_object = JsonCacheBackend(cache_file_path=json_cache_path)
    sqlite_backend_object = SqliteCacheBackend(database_file_path=sqlite_cache_path)

    for (
        file_path_string,
        cache_entry_dictionary,
    ) in json_backend_object.cache_data_dictionary.items():
        sqlite_backend_object.update_cache_entry(
            file_path_string=file_path_string,
            modification_time=cache_entry_dictionary["modification_time"],
            metadata=cache_entry_dictionary["metadata"],
        )

    sqlite_backend_object.finalize_cache()

    migrated_backup_path: Path = json_cache_path.with_suffix(".json.migrated")
    with contextlib.suppress(OSError):
        json_cache_path.rename(migrated_backup_path)
        logger.info(f"Backed up legacy JSON cache to {migrated_backup_path}")


def _initialize_cache_backend(
    target_directory_path: Path, discovered_files_list: list[Path]
) -> CacheBackendProtocol:
    """Determines and returns the appropriate cache backend (JSON or SQLite)."""
    hidden_directory_path: Path = target_directory_path / ".esm"
    hidden_directory_path.mkdir(parents=True, exist_ok=True)

    json_cache_path: Path = hidden_directory_path / ".esm-cache.json"
    sqlite_cache_path: Path = hidden_directory_path / ".esm-cache.db"

    database_already_exists_boolean: bool = sqlite_cache_path.exists()

    if database_already_exists_boolean:
        return SqliteCacheBackend(database_file_path=sqlite_cache_path)

    total_files_integer: int = len(discovered_files_list)
    dataset_is_massive_boolean: bool = (
        total_files_integer > MASSIVE_FILE_COUNT_THRESHOLD
    )

    if not dataset_is_massive_boolean:
        return JsonCacheBackend(cache_file_path=json_cache_path)

    if json_cache_path.exists():
        _migrate_json_to_sqlite(
            json_cache_path=json_cache_path, sqlite_cache_path=sqlite_cache_path
        )

    return SqliteCacheBackend(database_file_path=sqlite_cache_path)


def scan_directory(
    target_directory_path: Path,
    include_pattern_string: str = "*",
    exclude_pattern_string: str = "",
) -> list[FileMetadata]:
    """Recursively finds all files and extracts metadata."""
    logger.info(f"Starting directory scan at root path: {target_directory_path}")

    if not _validate_target_directory(target_directory_path):
        return []

    data_files_generator = itertools.chain(
        target_directory_path.rglob("*.nc"), target_directory_path.rglob("*.zarr")
    )
    all_discovered_files_list: list[Path] = list(data_files_generator)

    cache_backend_object: CacheBackendProtocol = _initialize_cache_backend(
        target_directory_path=target_directory_path,
        discovered_files_list=all_discovered_files_list,
    )

    found_metadata_list: list[FileMetadata] = []
    files_to_scan_list: list[Path] = []

    for data_file_path in all_discovered_files_list:
        needs_scan_boolean, cached_metadata = _process_file_for_scanning(
            data_file_path=data_file_path,
            include_pattern_string=include_pattern_string,
            exclude_pattern_string=exclude_pattern_string,
            cache_backend_object=cache_backend_object,
        )

        if needs_scan_boolean:
            files_to_scan_list.append(data_file_path)
        elif cached_metadata is not None:
            found_metadata_list.append(cached_metadata)

    parallel_results_list: list[FileMetadata | None] = process_files_in_parallel(
        files_to_scan_list=files_to_scan_list
    )

    _update_cache_with_results(
        files_to_scan_list=files_to_scan_list,
        parallel_results_list=parallel_results_list,
        cache_backend_object=cache_backend_object,
        found_metadata_list=found_metadata_list,
    )

    cache_backend_object.finalize_cache()

    total_files_processed_integer: int = len(found_metadata_list)
    logger.info(f"Scan complete. Processed {total_files_processed_integer} files.")

    return found_metadata_list

"""
Isolate static configurations, file cache mechanisms, and runtime parameter maps.
"""

import json
import logging
import os
import threading
from importlib.resources import files
from pathlib import Path
from typing import Final, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConfigError",
    "ConfigurationManager",
    "PipelineSettings",
    "settings_engine",
]

logger: Final[logging.Logger] = logging.getLogger(__name__)

STORAGE_DIR: Final[Path] = Path("data")
RUNTIME_SETTINGS_FILE: Final[Path] = STORAGE_DIR / "runtime_settings.json"


class ConfigError(Exception):
    """Unified base domain exception managing architecture configuration issues."""


class PipelineSettings(BaseModel):
    """Validates global operational parameters and third-party credential states."""

    model_config = ConfigDict(validate_assignment=True)

    llm_temperature: float = Field(0.2, ge=0.0, le=1.0)
    api_key_input: str = Field("")
    generator_system_prompt: str = Field("")
    judge_system_prompt: str = Field("")
    database_endpoint: str = Field("sqlite+aiosqlite:///data/tasks.db")

    def __str__(self) -> str:
        return f"PipelineSettings(temp={self.llm_temperature})"

    def __repr__(self) -> str:
        return f"PipelineSettings({self.model_dump_json()})"


class ConfigurationManager:
    """Thread-safe context orchestrator resolving factory baseline parameters."""

    __slots__ = ("_active_settings", "_baselines", "_lock")

    def __init__(self) -> None:
        self._lock: Final[threading.Lock] = threading.Lock()
        self._baselines: dict[str, str] = self._load_yaml_baselines()
        self._active_settings: PipelineSettings = self._initialize_state()

    def __str__(self) -> str:
        return "ConfigurationManager(Engine=Active)"

    def __repr__(self) -> str:
        return f"ConfigurationManager(_active_settings={self._active_settings!r})"

    def _load_yaml_baselines(self) -> dict[str, str]:
        """Reads static deployment blueprints from project layout file layers."""
        yaml_path: Final[Path] = (
            Path(str(files("backend.esm_data"))) / "templates.yaml"
        )

        if not yaml_path.exists():
            return {"generator_prompt": "", "judge_prompt": ""}

        try:
            raw_text = yaml_path.read_text(encoding="utf-8")
        except OSError as err:
            raise ConfigError(f"Failed to read file: {yaml_path}") from err

        try:
            raw = yaml.safe_load(raw_text)
        except yaml.YAMLError as err:
            raise ConfigError("Invalid YAML syntax parsed") from err

        return {
            "generator_prompt": str(
                raw.get("DEFAULT_LLM_INSTRUCTIONS", "")
            ).strip(),
            "judge_prompt": str(raw.get("JUDGE_INSTRUCTIONS", "")).strip(),
        }

    def _initialize_state(self) -> PipelineSettings:
        """Constructs starting operational contexts using environment fallbacks."""
        init_args: Final[dict[str, object]] = {
            "llm_temperature": 0.2,
            "api_key_input": os.environ.get(
                "ESM_API_KEY", "PROD_SECRET_TOKEN_MOCK"
            ),
            "generator_system_prompt": self._baselines["generator_prompt"],
            "judge_system_prompt": self._baselines["judge_prompt"],
            "database_endpoint": os.environ.get(
                "DATABASE_URL", "sqlite+aiosqlite:///data/tasks.db"
            ),
        }

        if not RUNTIME_SETTINGS_FILE.exists():
            return PipelineSettings(**init_args)

        try:
            with open(RUNTIME_SETTINGS_FILE, encoding="utf-8") as f:
                file_data = cast(dict[str, object], json.load(f))
        except (OSError, json.JSONDecodeError) as err:
            logger.warning("Dynamic rules deserialization aborted: %s", err)
            return PipelineSettings(**init_args)

        merged_args = {
            key: file_data.get(key, default_val)
            for key, default_val in init_args.items()
        }
        return PipelineSettings(**merged_args)

    def _apply_field_update(self, key: str, value: object) -> None:
        """Mutates individual variables safely if modifications are confirmed."""
        if not hasattr(self._active_settings, key):
            return
        if getattr(self._active_settings, key) == value:
            return
        setattr(self._active_settings, key, value)
        logger.info(f"CONFIG: Variable '{key}' rewritten in active state.")

    def get_current(self) -> PipelineSettings:
        """Returns the isolated system configuration values data state."""
        with self._lock:
            return self._active_settings

    def update_runtime(self, updates: dict[str, object]) -> None:
        """Atomically synchronizes and commits runtime configuration updates."""
        with self._lock:
            for key, value in updates.items():
                self._apply_field_update(key, value)

            try:
                STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                raise ConfigError("Failed to verify folder schema") from err

            try:
                with open(
                    RUNTIME_SETTINGS_FILE, "w", encoding="utf-8"
                ) as f_out:
                    json.dump(
                        self._active_settings.model_dump(), f_out, indent=2
                    )
            except OSError as err:
                raise ConfigError("Failed to update tracking cache") from err

    def reset_to_factory_defaults(self) -> None:
        """Purges interactive file overrides, restoring pristine definitions."""
        with self._lock:
            self._baselines = self._load_yaml_baselines()
            self._active_settings.llm_temperature = 0.2
            self._active_settings.generator_system_prompt = self._baselines[
                "generator_prompt"
            ]
            self._active_settings.judge_system_prompt = self._baselines[
                "judge_prompt"
            ]

            if not RUNTIME_SETTINGS_FILE.exists():
                return

            try:
                RUNTIME_SETTINGS_FILE.unlink()
            except OSError as err:
                raise ConfigError("Failed to clear local cached rules") from err

            logger.info("System settings returned completely to baselines.")


settings_engine: Final[ConfigurationManager] = ConfigurationManager()

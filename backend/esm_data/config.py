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

    llm_temperature: float = Field(0.0, ge=0.0, le=1.0)
    api_key_input: str = Field("")
    generator_system_prompt: str = Field("")
    judge_system_prompt: str = Field("")
    yaml_system_prompt: str = Field("")
    database_endpoint: str = Field("sqlite+aiosqlite:///data/tasks.db")
    global_chosen_engine: str = Field("gemini")
    custom_key_name: str = Field("")
    recognized_provider: str = Field("")
    custom_api_keys: dict[str, str] = Field(default_factory=dict)
    custom_key_providers: dict[str, str] = Field(default_factory=dict)

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
        yaml_path: Final[Path] = Path(str(files("backend.esm_data"))) / "templates.yaml"

        if not yaml_path.exists():
            return {"generator_prompt": "", "judge_prompt": ""}

        try:
            raw_text = yaml_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ConfigError(f"Failed to read file: {yaml_path}") from error

        try:
            raw = yaml.safe_load(raw_text)
        except yaml.YAMLError as error:
            raise ConfigError("Invalid YAML syntax parsed") from error

        return {
            "generator_prompt": str(raw.get("DEFAULT_LLM_INSTRUCTIONS", "")).strip(),
            "judge_prompt": str(raw.get("JUDGE_INSTRUCTIONS", "")).strip(),
            "yaml_prompt": str(raw.get("YAML_CONTEXT_INSTRUCTIONS", "")).strip(),
        }

    def _initialize_state(self) -> PipelineSettings:
        """Constructs starting operational contexts using environment fallbacks."""
        init_args: Final[dict[str, object]] = {
            "llm_temperature": 0.0,
            "api_key_input": os.environ.get("ESM_API_KEY", "PROD_SECRET_TOKEN_MOCK"),
            "generator_system_prompt": self._baselines["generator_prompt"],
            "judge_system_prompt": self._baselines["judge_prompt"],
            "yaml_system_prompt": self._baselines["yaml_prompt"],
            "database_endpoint": os.environ.get(
                "DATABASE_URL", "sqlite+aiosqlite:///data/tasks.db"
            ),
            "global_chosen_engine": "gemini",
            "custom_key_name": "",
            "recognized_provider": "",
            "custom_api_keys": {},
            "custom_key_providers": {},
        }

        if not RUNTIME_SETTINGS_FILE.exists():
            return PipelineSettings(**init_args)

        try:
            with open(RUNTIME_SETTINGS_FILE, encoding="utf-8") as settings_file:
                file_data = cast(dict[str, object], json.load(settings_file))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Dynamic rules deserialization aborted: %s", error)
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

    def update_runtime(self, updates: dict[str, object]) -> None:  # noqa: C901
        """Atomically synchronizes and commits runtime configuration updates."""
        with self._lock:
            new_key = updates.get("api_key_input")
            new_name = updates.get("custom_key_name")
            new_provider = updates.get("recognized_provider")
            if new_key and new_name and new_provider:
                self._active_settings.custom_api_keys[str(new_name)] = str(new_key)

                # Merge into updates so it isn't overwritten
                providers_dict = updates.get("custom_key_providers")
                if providers_dict is None:
                    providers_dict = self._active_settings.custom_key_providers.copy()
                if isinstance(providers_dict, dict):
                    providers_dict[str(new_name)] = str(new_provider)
                updates["custom_key_providers"] = providers_dict

            for key, value in updates.items():
                if key in ("api_key_input", "custom_key_name", "recognized_provider"):
                    continue
                self._apply_field_update(key, value)

            keys_to_delete = [
                key
                for key in self._active_settings.custom_api_keys
                if key not in self._active_settings.custom_key_providers
            ]
            for key in keys_to_delete:
                del self._active_settings.custom_api_keys[key]

            try:
                STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise ConfigError("Failed to verify folder schema") from error

            try:
                with open(
                    RUNTIME_SETTINGS_FILE, "w", encoding="utf-8"
                ) as settings_file_out:
                    json.dump(
                        self._active_settings.model_dump(
                            exclude={"api_key_input", "custom_api_keys"}
                        ),
                        settings_file_out,
                        indent=2,
                    )
            except OSError as error:
                raise ConfigError("Failed to update tracking cache") from error

    def reset_to_factory_defaults(self) -> None:
        """Purges interactive file overrides, restoring pristine definitions."""
        with self._lock:
            self._baselines = self._load_yaml_baselines()
            self._active_settings.llm_temperature = 0.0
            self._active_settings.generator_system_prompt = self._baselines[
                "generator_prompt"
            ]
            self._active_settings.judge_system_prompt = self._baselines["judge_prompt"]
            self._active_settings.yaml_system_prompt = self._baselines["yaml_prompt"]
            self._active_settings.global_chosen_engine = "gemini"
            self._active_settings.custom_key_name = ""
            self._active_settings.recognized_provider = ""

            if not RUNTIME_SETTINGS_FILE.exists():
                return

            try:
                RUNTIME_SETTINGS_FILE.unlink()
            except OSError as error:
                raise ConfigError("Failed to clear local cached rules") from error

            logger.info("System settings returned completely to baselines.")


settings_engine: Final[ConfigurationManager] = ConfigurationManager()

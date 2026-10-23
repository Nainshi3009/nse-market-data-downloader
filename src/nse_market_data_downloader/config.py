"""Loading and validation for application configuration."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .datasets import DATASETS


class ConfigurationError(ValueError):
    """Raised when configuration is missing, malformed, or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Validated application settings."""

    config_path: Path
    output_dir: Path
    logs_dir: Path
    expected_columns: Mapping[str, tuple[str, ...]]
    request_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    automated_access_permitted: bool


def _number(
    settings: dict[str, Any],
    name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    """Read a finite numeric setting within the given inclusive range."""
    value = settings.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"'{name}' must be a number.")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ConfigurationError(
            f"'{name}' must be between {minimum} and {maximum}."
        )
    return float(value)


def load_config(config_path: str | Path = "config.json") -> AppConfig:
    """Read and validate JSON settings, resolving output paths from the file.

    Relative output directories are anchored to the configuration file's
    directory rather than whichever directory happens to be the current one.
    """
    resolved_config_path = Path(config_path).expanduser().resolve()
    try:
        with resolved_config_path.open(encoding="utf-8") as config_file:
            settings = json.load(config_file)
    except FileNotFoundError as error:
        raise ConfigurationError(
            f"Configuration file not found: {resolved_config_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON in {resolved_config_path}: {error.msg} "
            f"(line {error.lineno}, column {error.colno})."
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Could not read configuration file {resolved_config_path}: {error}"
        ) from error

    if not isinstance(settings, dict):
        raise ConfigurationError("Configuration must be a JSON object.")

    output_value = settings.get("output_dir")
    if not isinstance(output_value, str) or not output_value.strip():
        raise ConfigurationError("'output_dir' must be a non-empty string.")
    if "\0" in output_value:
        raise ConfigurationError("'output_dir' must not contain a null byte.")
    output_path = Path(output_value).expanduser()
    if not output_path.is_absolute():
        output_path = resolved_config_path.parent / output_path

    logs_value = settings.get("logs_dir")
    if not isinstance(logs_value, str) or not logs_value.strip():
        raise ConfigurationError("'logs_dir' must be a non-empty string.")
    if "\0" in logs_value:
        raise ConfigurationError("'logs_dir' must not contain a null byte.")
    logs_path = Path(logs_value).expanduser()
    if not logs_path.is_absolute():
        logs_path = resolved_config_path.parent / logs_path

    columns_setting = settings.get("expected_columns", {})
    if not isinstance(columns_setting, dict):
        raise ConfigurationError("'expected_columns' must be a JSON object.")
    expected_columns: dict[str, tuple[str, ...]] = {}
    for dataset_id, columns in columns_setting.items():
        if dataset_id not in DATASETS:
            raise ConfigurationError(
                f"'expected_columns' contains unknown dataset '{dataset_id}'."
            )
        if (
            not isinstance(columns, list)
            or not columns
            or any(not isinstance(column, str) or not column.strip()
                   for column in columns)
            or len(set(columns)) != len(columns)
        ):
            raise ConfigurationError(
                f"'expected_columns.{dataset_id}' must be a non-empty list of "
                "unique, non-empty column names."
            )
        expected_columns[dataset_id] = tuple(columns)

    retries = settings.get("max_retries")
    if isinstance(retries, bool) or not isinstance(retries, int):
        raise ConfigurationError("'max_retries' must be an integer.")
    if not 0 <= retries <= 5:
        raise ConfigurationError("'max_retries' must be between 0 and 5.")

    permission = settings.get("automated_access_permitted")
    if not isinstance(permission, bool):
        raise ConfigurationError(
            "'automated_access_permitted' must be true or false."
        )

    return AppConfig(
        config_path=resolved_config_path,
        output_dir=output_path.resolve(),
        logs_dir=logs_path.resolve(),
        expected_columns=expected_columns,
        request_timeout_seconds=_number(
            settings,
            "request_timeout_seconds",
            minimum=0.1,
            maximum=300,
        ),
        max_retries=retries,
        retry_backoff_seconds=_number(
            settings,
            "retry_backoff_seconds",
            minimum=0,
            maximum=60,
        ),
        automated_access_permitted=permission,
    )

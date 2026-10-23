"""Safe CSV storage for validated market-data results."""

from datetime import date, datetime
import logging
import os
from pathlib import Path
import tempfile

import pandas as pd

from .config import AppConfig
from .datasets import DATASETS
from .validation import DataValidationError, ValidationResult, validate_dataset

logger = logging.getLogger(__name__)


class StorageError(OSError):
    """Raised when a validated dataset cannot be safely saved."""


class OutputFileExistsError(StorageError):
    """Raised instead of overwriting a dataset already saved for that date."""


def save_dataset(
    dataset_id: str,
    validated: ValidationResult,
    trading_date: date,
    config: AppConfig,
) -> Path:
    """Atomically save one validated dataset as a dated CSV file.

    The deterministic filename is ``<dataset-id>_<YYYY-MM-DD>.csv``. If that
    file already exists, this function fails without overwriting it or making
    an alternate copy. A temporary file is written in the destination folder
    and published with an atomic, no-overwrite hard link.
    """
    file_path: Path | None = None
    try:
        if dataset_id not in DATASETS:
            raise StorageError(f"Unknown dataset '{dataset_id}'.")
        if not isinstance(validated, ValidationResult):
            raise StorageError(
                "Only a ValidationResult from dataset validation can be saved."
            )
        if not isinstance(trading_date, date) or isinstance(trading_date, datetime):
            raise StorageError("trading_date must be a datetime.date value.")

        checked = validate_dataset(validated.data, validated.expected_columns)
        if checked.duplicates_removed:
            raise StorageError(
                "ValidationResult contains duplicate rows; validate data before saving."
            )

        output_dir = config.output_dir
        file_path = output_dir / f"{dataset_id}_{trading_date.isoformat()}.csv"
        logger.info(
            "Preparing CSV output.",
            extra={
                "event": "storage_started",
                "operation": "save_csv",
                "status": "started",
                "dataset_id": dataset_id,
                "file_path": str(file_path),
                "record_count": len(checked.data),
            },
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        if file_path.exists():
            raise OutputFileExistsError(
                f"Output already exists for {dataset_id} on "
                f"{trading_date.isoformat()}: {file_path}"
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix=".tmp",
                prefix=f".{dataset_id}_",
                dir=output_dir,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                checked.data.to_csv(temporary_file, index=False)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.link(temporary_path, file_path)
            except FileExistsError as error:
                raise OutputFileExistsError(
                    f"Output already exists for {dataset_id} on "
                    f"{trading_date.isoformat()}: {file_path}"
                ) from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    logger.error(
                        "Could not remove temporary CSV file.",
                        extra={
                            "event": "storage_cleanup_failed",
                            "operation": "save_csv",
                            "status": "failure",
                            "dataset_id": dataset_id,
                            "file_path": str(temporary_path),
                            "error_type": type(cleanup_error).__name__,
                        },
                    )

        logger.info(
            "CSV saved successfully.",
            extra={
                "event": "storage_succeeded",
                "operation": "save_csv",
                "status": "success",
                "dataset_id": dataset_id,
                "file_path": str(file_path),
                "record_count": len(checked.data),
                "duplicates_removed": validated.duplicates_removed,
            },
        )
        return file_path
    except OutputFileExistsError as error:
        logger.error(
            "CSV output was not overwritten.",
            extra={
                "event": "storage_failed",
                "operation": "save_csv",
                "status": "failure",
                "dataset_id": dataset_id,
                "file_path": str(file_path) if file_path else "",
                "error_type": type(error).__name__,
            },
        )
        raise
    except (DataValidationError, StorageError) as error:
        logger.error(
            "CSV storage rejected the dataset: %s",
            error,
            extra={
                "event": "storage_failed",
                "operation": "save_csv",
                "status": "failure",
                "dataset_id": dataset_id,
                "file_path": str(file_path) if file_path else "",
                "error_type": type(error).__name__,
            },
        )
        if isinstance(error, StorageError):
            raise
        raise StorageError(f"Dataset validation failed before saving: {error}") from error
    except (OSError, TypeError, ValueError) as error:
        logger.exception(
            "CSV write failed.",
            extra={
                "event": "storage_failed",
                "operation": "save_csv",
                "status": "failure",
                "dataset_id": dataset_id,
                "file_path": str(file_path) if file_path else "",
                "error_type": type(error).__name__,
            },
        )
        raise StorageError(
            f"Could not save dataset '{dataset_id}'"
            f"{f' to {file_path}' if file_path else ''}: {error}"
        ) from error

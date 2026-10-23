"""Command-line entry point for the NSE market-data downloader."""

import argparse
from datetime import date
from io import BytesIO
import logging
import sys
from typing import Sequence

import pandas as pd

from .acquisition import AcquisitionError, AcquiredPayload, acquire_dataset
from .config import AppConfig, ConfigurationError, load_config
from .datasets import DATASETS
from .logging_config import configure_logging
from .storage import StorageError, save_dataset
from .validation import DataValidationError, validate_dataset

logger = logging.getLogger(__name__)


class DatasetFormatError(ValueError):
    """Raised when an acquired response cannot safely become a dataset."""


def _parse_date(value: str) -> date:
    """Parse an ISO-8601 calendar date for output filenames."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'; use YYYY-MM-DD."
        ) from error


def _parse_csv_payload(payload: AcquiredPayload) -> pd.DataFrame:
    """Parse explicitly declared CSV bytes without accepting HTML or guessing JSON."""
    if payload.content_type not in {"text/csv", "application/csv"}:
        raise DatasetFormatError(
            f"Dataset '{payload.dataset_id}' returned {payload.content_type}; "
            "the JSON response shape has not been verified."
        )
    try:
        return pd.read_csv(BytesIO(payload.content))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
        raise DatasetFormatError(
            f"Could not parse CSV for '{payload.dataset_id}': {error}"
        ) from error


def _download_one(
    dataset_id: str,
    config: AppConfig,
    trading_date: date,
) -> None:
    """Acquire, validate, and store one dataset or raise a useful error."""
    payload = acquire_dataset(dataset_id, config)
    data = _parse_csv_payload(payload)
    expected_columns = config.expected_columns.get(dataset_id)
    if not expected_columns:
        raise DatasetFormatError(
            f"Expected columns for '{dataset_id}' have not been confirmed. "
            "No CSV was written."
        )
    validated = validate_dataset(data, expected_columns)
    saved_path = save_dataset(dataset_id, validated, trading_date, config)
    logger.info(
        "Dataset download completed.",
        extra={
            "event": "dataset_completed",
            "operation": "download_dataset",
            "status": "success",
            "dataset_id": dataset_id,
            "file_path": str(saved_path),
            "record_count": len(validated.data),
            "duplicates_removed": validated.duplicates_removed,
        },
    )
    print(f"SUCCESS {dataset_id}: {len(validated.data)} records -> {saved_path}")


def build_parser() -> argparse.ArgumentParser:
    """Create the application argument parser."""
    parser = argparse.ArgumentParser(
        description="Download permitted NSE market data into dated CSV files."
    )
    parser.add_argument(
        "--dataset",
        choices=("all", *DATASETS.keys()),
        default="all",
        help="dataset to download (default: all)",
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=date.today(),
        help="trading date for output filenames in YYYY-MM-DD format "
        "(default: today's local date)",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="path to the JSON configuration file (default: config.json)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run selected downloads and continue after per-dataset failures."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        configure_logging(config.logs_dir)
    except (ConfigurationError, OSError) as error:
        print(f"Configuration or logging error: {error}", file=sys.stderr)
        return 2

    selected = tuple(DATASETS) if args.dataset == "all" else (args.dataset,)
    failures = 0
    logger.info(
        "Starting dataset run.",
        extra={
            "event": "run_started",
            "operation": "download",
            "status": "started",
            "dataset_count": len(selected),
        },
    )
    for dataset_id in selected:
        try:
            _download_one(dataset_id, config, args.date)
        except (
            AcquisitionError,
            DatasetFormatError,
            DataValidationError,
            StorageError,
        ) as error:
            failures += 1
            logger.error(
                "Dataset download failed: %s",
                error,
                extra={
                    "event": "dataset_failed",
                    "operation": "download_dataset",
                    "status": "failure",
                    "dataset_id": dataset_id,
                    "error_type": type(error).__name__,
                },
            )
            print(f"FAILED {dataset_id}: {error}", file=sys.stderr)

    logger.info(
        "Dataset run finished.",
        extra={
            "event": "run_finished",
            "operation": "download",
            "status": "failure" if failures else "success",
            "dataset_count": len(selected),
        },
    )
    return 1 if failures else 0

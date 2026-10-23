"""Validation and exact-duplicate removal for tabular market data."""

from dataclasses import dataclass
import logging
from collections.abc import Sequence

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidationError(ValueError):
    """Raised when a dataset is empty or does not meet its expected schema."""


@dataclass(frozen=True)
class ValidationResult:
    """Validated data and the number of exact duplicate rows removed."""

    data: pd.DataFrame
    duplicates_removed: int
    expected_columns: tuple[str, ...]


def validate_dataset(
    data: pd.DataFrame,
    expected_columns: Sequence[str],
) -> ValidationResult:
    """Check dataset shape/schema and remove repeated identical rows.

    Expected column names are supplied by the caller because the NSE page
    routes do not, by themselves, establish a stable data schema.
    """
    if not isinstance(data, pd.DataFrame):
        raise DataValidationError("Dataset must be provided as a pandas DataFrame.")
    if not expected_columns:
        raise DataValidationError(
            "At least one expected column must be provided; no schema was assumed."
        )
    if any(not isinstance(column, str) or not column.strip()
           for column in expected_columns):
        raise DataValidationError("Expected column names must be non-empty strings.")
    if len(set(expected_columns)) != len(expected_columns):
        raise DataValidationError("Expected column names must not contain duplicates.")
    if data.columns.has_duplicates:
        raise DataValidationError("Dataset contains duplicate column names.")

    if data.empty:
        raise DataValidationError("Dataset contains no rows.")

    missing = [column for column in expected_columns if column not in data.columns]
    if missing:
        raise DataValidationError(
            "Dataset is missing expected column(s): " + ", ".join(missing)
        )

    non_blank_data = data.replace(r"^\s*$", pd.NA, regex=True)
    if non_blank_data.dropna(how="all").empty:
        raise DataValidationError("Dataset contains no non-empty data values.")

    original_count = len(data)
    unique_data = data.drop_duplicates().copy()
    duplicates_removed = original_count - len(unique_data)
    logger.info(
        "Validated dataset: %d records; removed %d exact duplicate rows.",
        len(unique_data),
        duplicates_removed,
    )
    return ValidationResult(
        data=unique_data,
        duplicates_removed=duplicates_removed,
        expected_columns=tuple(expected_columns),
    )

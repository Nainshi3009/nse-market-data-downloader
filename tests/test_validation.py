"""Tests for schema validation and duplicate handling."""

import pandas as pd
import pytest

from nse_market_data_downloader.validation import (
    DataValidationError,
    validate_dataset,
)


def test_validates_expected_columns_and_removes_exact_duplicates():
    frame = pd.DataFrame(
        {
            "Example name": ["First", "Second", "First"],
            "Example value": [10, 20, 10],
        }
    )

    result = validate_dataset(
        frame,
        expected_columns=["Example name", "Example value"],
    )

    assert len(result.data) == 2
    assert result.duplicates_removed == 1
    assert list(result.data.columns) == ["Example name", "Example value"]
    assert len(frame) == 3


def test_keeps_rows_that_share_only_some_values():
    frame = pd.DataFrame(
        {
            "Example name": ["Same", "Same"],
            "Example value": [10, 11],
        }
    )

    result = validate_dataset(frame, ["Example name", "Example value"])

    assert len(result.data) == 2
    assert result.duplicates_removed == 0


@pytest.mark.parametrize(
    ("frame", "columns", "message"),
    [
        (pd.DataFrame(), ["Example name"], "no rows"),
        (pd.DataFrame({"Other": [1]}), ["Example name"], "missing expected"),
        (pd.DataFrame({"Example name": [" ", "\t"]}),
         ["Example name"], "no non-empty data"),
        (pd.DataFrame({"Example name": ["Value"]}), [], "At least one"),
        (pd.DataFrame({"Example name": ["Value"]}),
         ["Example name", "Example name"], "must not contain duplicates"),
    ],
)
def test_rejects_invalid_dataset(frame, columns, message):
    with pytest.raises(DataValidationError, match=message):
        validate_dataset(frame, columns)


def test_rejects_duplicate_dataframe_column_names():
    frame = pd.DataFrame([["first", "second"]], columns=["Name", "Name"])

    with pytest.raises(DataValidationError, match="duplicate column names"):
        validate_dataset(frame, ["Name"])


def test_rejects_non_dataframe_input():
    with pytest.raises(DataValidationError, match="pandas DataFrame"):
        validate_dataset([{"Name": "Example"}], ["Name"])

"""Tests for safe CSV creation and application logging."""

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from nse_market_data_downloader.config import AppConfig
from nse_market_data_downloader.logging_config import configure_logging
from nse_market_data_downloader.storage import (
    OutputFileExistsError,
    StorageError,
    save_dataset,
)
from nse_market_data_downloader.validation import (
    ValidationResult,
    validate_dataset,
)


def _config(tmp_path: Path, *, output_dir: Path | None = None) -> AppConfig:
    return AppConfig(
        config_path=tmp_path / "config.json",
        output_dir=output_dir or tmp_path / "output",
        logs_dir=tmp_path / "logs",
        expected_columns={},
        request_timeout_seconds=20,
        max_retries=3,
        retry_backoff_seconds=1,
        automated_access_permitted=False,
    )


def _validated_data() -> ValidationResult:
    return validate_dataset(
        pd.DataFrame({"Example name": ["One", "Two"], "Value": [10, 20]}),
        ["Example name", "Value"],
    )


@pytest.mark.parametrize(
    "dataset_id",
    [
        "top-gainers-losers",
        "upper-band-hitters",
        "volume-gainers-spurts",
        "52-week-high-equity-market",
    ],
)
def test_save_dataset_creates_named_dated_csv(tmp_path, dataset_id):
    result = save_dataset(
        dataset_id, _validated_data(), date(2026, 10, 23), _config(tmp_path)
    )

    assert result == (
        tmp_path / "output" / f"{dataset_id}_2026-10-23.csv"
    )
    saved = pd.read_csv(result)
    assert saved.to_dict(orient="records") == [
        {"Example name": "One", "Value": 10},
        {"Example name": "Two", "Value": 20},
    ]


def test_existing_file_is_not_overwritten_or_duplicated(tmp_path):
    config = _config(tmp_path)
    existing = config.output_dir / "top-gainers-losers_2026-10-23.csv"
    existing.parent.mkdir(parents=True)
    existing.write_text("original content\n", encoding="utf-8")

    with pytest.raises(OutputFileExistsError, match="already exists"):
        save_dataset(
            "top-gainers-losers",
            _validated_data(),
            date(2026, 10, 23),
            config,
        )

    assert existing.read_text(encoding="utf-8") == "original content\n"
    assert list(config.output_dir.glob("*.csv")) == [existing]


def test_failed_csv_write_leaves_no_final_or_temporary_file(tmp_path, monkeypatch):
    def fail_write(self, path_or_buf=None, *args, **kwargs):
        path_or_buf.write("partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_write)
    config = _config(tmp_path)

    with pytest.raises(StorageError, match="simulated disk failure"):
        save_dataset(
            "upper-band-hitters",
            _validated_data(),
            date(2026, 10, 23),
            config,
        )

    assert not list(config.output_dir.glob("*.csv"))
    assert not list(config.output_dir.glob("*.tmp"))
    assert not list(config.output_dir.glob(".*.tmp"))


def test_rejects_unvalidated_or_empty_data(tmp_path):
    config = _config(tmp_path)
    with pytest.raises(StorageError, match="ValidationResult"):
        save_dataset(
            "volume-gainers-spurts",
            pd.DataFrame({"Example name": ["Not validated"]}),
            date(2026, 10, 23),
            config,
        )

    empty_result = ValidationResult(
        data=pd.DataFrame(),
        duplicates_removed=0,
        expected_columns=("Example name",),
    )
    with pytest.raises(StorageError, match="validation failed"):
        save_dataset(
            "volume-gainers-spurts",
            empty_result,
            date(2026, 10, 23),
            config,
        )

    assert not config.output_dir.exists()


def test_invalid_output_directory_is_reported(tmp_path):
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("file", encoding="utf-8")

    with pytest.raises(StorageError, match="Could not save"):
        save_dataset(
            "52-week-high-equity-market",
            _validated_data(),
            date(2026, 10, 23),
            _config(tmp_path, output_dir=output_file),
        )


def test_logging_writes_timestamped_structured_events_and_console_output(
    tmp_path, capsys
):
    logs_dir = tmp_path / "configured-logs"
    log_path = configure_logging(logs_dir)

    saved_path = save_dataset(
        "top-gainers-losers",
        _validated_data(),
        date(2026, 10, 23),
        _config(tmp_path),
    )

    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    succeeded = next(
        item for item in entries if item.get("event") == "storage_succeeded"
    )
    assert succeeded["timestamp"]
    assert succeeded["operation"] == "save_csv"
    assert succeeded["status"] == "success"
    assert succeeded["record_count"] == 2
    assert succeeded["file_path"] == str(saved_path)
    assert "CSV saved successfully" in capsys.readouterr().err

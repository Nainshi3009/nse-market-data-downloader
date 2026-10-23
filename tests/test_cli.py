"""Tests for the command-line interface without live NSE requests."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from nse_market_data_downloader import cli
from nse_market_data_downloader.acquisition import (
    AccessNotPermittedError,
    AcquisitionError,
    AcquiredPayload,
)
from nse_market_data_downloader.config import AppConfig


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        config_path=tmp_path / "config.json",
        output_dir=tmp_path / "output",
        logs_dir=tmp_path / "logs",
        expected_columns={},
        request_timeout_seconds=20,
        max_retries=3,
        retry_backoff_seconds=1,
        automated_access_permitted=False,
    )


def test_parser_defaults_to_all_datasets_and_today():
    args = cli.build_parser().parse_args([])

    assert args.dataset == "all"
    assert args.date == date.today()


def test_parser_accepts_one_dataset_and_explicit_date():
    args = cli.build_parser().parse_args(
        ["--dataset", "upper-band-hitters", "--date", "2026-10-23"]
    )

    assert args.dataset == "upper-band-hitters"
    assert args.date == date(2026, 10, 23)


def test_parser_rejects_malformed_date():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--date", "23-10-2026"])


def test_all_selection_continues_when_access_fails(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    acquire = Mock(side_effect=AccessNotPermittedError("access disabled"))
    monkeypatch.setattr(cli, "acquire_dataset", acquire)

    result = cli.main(["--dataset", "all", "--date", "2026-10-23"])

    assert result == 1
    assert acquire.call_count == 4
    assert capsys.readouterr().err.count("FAILED ") == 4


def test_individual_selection_calls_only_selected_dataset(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "load_config", Mock(return_value=_config(tmp_path)))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    acquire = Mock(side_effect=AccessNotPermittedError("access disabled"))
    monkeypatch.setattr(cli, "acquire_dataset", acquire)

    result = cli.main(["--dataset", "volume-gainers-spurts"])

    assert result == 1
    acquire.assert_called_once()
    assert acquire.call_args.args[0] == "volume-gainers-spurts"
    assert "FAILED volume-gainers-spurts" in capsys.readouterr().err


def test_successful_permitted_csv_flow_validates_then_saves(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path)
    config = AppConfig(
        config_path=config.config_path,
        output_dir=config.output_dir,
        logs_dir=config.logs_dir,
        expected_columns={"top-gainers-losers": ("Example name", "Value")},
        request_timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        retry_backoff_seconds=config.retry_backoff_seconds,
        automated_access_permitted=True,
    )
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    monkeypatch.setattr(
        cli,
        "acquire_dataset",
        Mock(
            return_value=AcquiredPayload(
                "top-gainers-losers",
                b"Example name,Value\nOne,10\n",
                "text/csv",
            )
        ),
    )
    saved_path = tmp_path / "output" / "top-gainers-losers_2026-10-23.csv"
    save = Mock(return_value=saved_path)
    monkeypatch.setattr(cli, "save_dataset", save)

    result = cli.main(
        ["--dataset", "top-gainers-losers", "--date", "2026-10-23"]
    )

    assert result == 0
    save.assert_called_once()
    assert save.call_args.args[1].expected_columns == ("Example name", "Value")
    assert "SUCCESS top-gainers-losers" in capsys.readouterr().out


def test_csv_without_confirmed_schema_is_not_saved(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", Mock(return_value=_config(tmp_path)))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    monkeypatch.setattr(
        cli,
        "acquire_dataset",
        Mock(
            return_value=AcquiredPayload(
                "upper-band-hitters",
                b"Unknown,Columns\nvalue,10\n",
                "text/csv",
            )
        ),
    )
    save = Mock()
    monkeypatch.setattr(cli, "save_dataset", save)

    result = cli.main(["--dataset", "upper-band-hitters"])

    assert result == 1
    save.assert_not_called()
    assert "Expected columns" in capsys.readouterr().err


def test_invalid_dataset_response_cannot_create_csv(
    tmp_path, monkeypatch, capsys
):
    base_config = _config(tmp_path)
    config = AppConfig(
        config_path=base_config.config_path,
        output_dir=base_config.output_dir,
        logs_dir=base_config.logs_dir,
        expected_columns={"top-gainers-losers": ("Expected", "Value")},
        request_timeout_seconds=base_config.request_timeout_seconds,
        max_retries=base_config.max_retries,
        retry_backoff_seconds=base_config.retry_backoff_seconds,
        automated_access_permitted=True,
    )
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    monkeypatch.setattr(
        cli,
        "acquire_dataset",
        Mock(
            return_value=AcquiredPayload(
                "top-gainers-losers",
                b"Unexpected,Columns\nvalue,10\n",
                "text/csv",
            )
        ),
    )

    result = cli.main(
        ["--dataset", "top-gainers-losers", "--date", "2026-10-23"]
    )

    assert result == 1
    assert not config.output_dir.exists()
    assert "missing expected column" in capsys.readouterr().err


def test_acquisition_failure_cannot_create_csv(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    acquire = Mock(side_effect=AcquisitionError("network unavailable"))
    monkeypatch.setattr(cli, "acquire_dataset", acquire)

    result = cli.main(
        ["--dataset", "top-gainers-losers", "--date", "2026-10-23"]
    )

    assert result == 1
    assert not config.output_dir.exists()
    acquire.assert_called_once()
    assert "network unavailable" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "content_type", "error_text"),
    [
        (b"", "text/csv", "Could not parse CSV"),
        (b'Example name,Value\n"unfinished,10', "text/csv", "Could not parse CSV"),
        (b"<html>not market data</html>", "text/html", "returned text/html"),
        (b'{"items": []}', "application/json", "JSON response shape"),
    ],
)
def test_invalid_or_empty_response_cannot_create_csv(
    tmp_path, monkeypatch, capsys, content, content_type, error_text
):
    base_config = _config(tmp_path)
    config = AppConfig(
        config_path=base_config.config_path,
        output_dir=base_config.output_dir,
        logs_dir=base_config.logs_dir,
        expected_columns={"top-gainers-losers": ("Example name", "Value")},
        request_timeout_seconds=base_config.request_timeout_seconds,
        max_retries=base_config.max_retries,
        retry_backoff_seconds=base_config.retry_backoff_seconds,
        automated_access_permitted=True,
    )
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    monkeypatch.setattr(
        cli,
        "acquire_dataset",
        Mock(
            return_value=AcquiredPayload(
                "top-gainers-losers", content, content_type
            )
        ),
    )

    result = cli.main(
        ["--dataset", "top-gainers-losers", "--date", "2026-10-23"]
    )

    assert result == 1
    assert not config.output_dir.exists()
    assert error_text in capsys.readouterr().err


def test_successful_mocked_response_creates_actual_csv(tmp_path, monkeypatch, capsys):
    base_config = _config(tmp_path)
    config = AppConfig(
        config_path=base_config.config_path,
        output_dir=base_config.output_dir,
        logs_dir=base_config.logs_dir,
        expected_columns={"top-gainers-losers": ("Example name", "Value")},
        request_timeout_seconds=base_config.request_timeout_seconds,
        max_retries=base_config.max_retries,
        retry_backoff_seconds=base_config.retry_backoff_seconds,
        automated_access_permitted=True,
    )
    monkeypatch.setattr(cli, "load_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "configure_logging", Mock())
    acquire = Mock(
        return_value=AcquiredPayload(
            "top-gainers-losers",
            b"Example name,Value\nOne,10\n",
            "text/csv",
        )
    )
    monkeypatch.setattr(cli, "acquire_dataset", acquire)

    result = cli.main(
        ["--dataset", "top-gainers-losers", "--date", "2026-10-23"]
    )

    csv_path = config.output_dir / "top-gainers-losers_2026-10-23.csv"
    assert result == 0
    assert csv_path.is_file()
    assert pd.read_csv(csv_path).to_dict(orient="records") == [
        {"Example name": "One", "Value": 10}
    ]
    acquire.assert_called_once()
    assert "SUCCESS top-gainers-losers: 1 records" in capsys.readouterr().out


def test_config_failure_returns_error_without_acquiring(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "load_config", Mock(side_effect=cli.ConfigurationError("bad config"))
    )
    acquire = Mock()
    monkeypatch.setattr(cli, "acquire_dataset", acquire)

    result = cli.main([])

    assert result == 2
    acquire.assert_not_called()
    assert "bad config" in capsys.readouterr().err

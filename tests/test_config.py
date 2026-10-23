"""Tests for configuration loading and validation."""

import json

import pytest

from nse_market_data_downloader.config import ConfigurationError, load_config


def _write_config(tmp_path, settings):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def _valid_settings():
    return {
        "output_dir": "market-output",
        "logs_dir": "market-logs",
        "expected_columns": {},
        "request_timeout_seconds": 20,
        "max_retries": 3,
        "retry_backoff_seconds": 1,
        "automated_access_permitted": False,
    }


def test_load_config_resolves_relative_output_from_config_directory(tmp_path):
    config_path = _write_config(tmp_path, _valid_settings())

    config = load_config(config_path)

    assert config.config_path == config_path.resolve()
    assert config.output_dir == (tmp_path / "market-output").resolve()
    assert config.logs_dir == (tmp_path / "market-logs").resolve()
    assert config.max_retries == 3
    assert config.automated_access_permitted is False


def test_load_config_reports_missing_file(tmp_path):
    with pytest.raises(ConfigurationError, match="not found"):
        load_config(tmp_path / "missing.json")


def test_load_config_reports_malformed_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Invalid JSON"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("output_dir", "", "output_dir"),
        ("logs_dir", "", "logs_dir"),
        ("expected_columns", ["not", "an", "object"], "expected_columns"),
        ("request_timeout_seconds", 0, "request_timeout_seconds"),
        ("request_timeout_seconds", float("nan"), "request_timeout_seconds"),
        ("retry_backoff_seconds", float("inf"), "retry_backoff_seconds"),
        ("max_retries", 6, "max_retries"),
        ("max_retries", True, "max_retries"),
        ("retry_backoff_seconds", -1, "retry_backoff_seconds"),
        ("automated_access_permitted", "false", "automated_access_permitted"),
    ],
)
def test_load_config_rejects_invalid_settings(tmp_path, key, value, message):
    settings = _valid_settings()
    settings[key] = value
    config_path = _write_config(tmp_path, settings)

    with pytest.raises(ConfigurationError, match=message):
        load_config(config_path)


def test_load_config_requires_automated_access_setting(tmp_path):
    settings = _valid_settings()
    del settings["automated_access_permitted"]

    with pytest.raises(ConfigurationError, match="automated_access_permitted"):
        load_config(_write_config(tmp_path, settings))

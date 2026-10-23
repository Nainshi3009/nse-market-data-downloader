"""Mocked tests for safe HTTP acquisition behavior."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from nse_market_data_downloader.acquisition import (
    AccessDeniedError,
    AccessNotPermittedError,
    AcquisitionError,
    EmptyResponseError,
    HTTPStatusError,
    UnexpectedContentTypeError,
    acquire_dataset,
)
from nse_market_data_downloader.config import AppConfig


def _config(*, permitted=True, retries=2):
    return AppConfig(
        config_path=Path("config.json"),
        output_dir=Path("output"),
        logs_dir=Path("logs"),
        expected_columns={},
        request_timeout_seconds=0.25,
        max_retries=retries,
        retry_backoff_seconds=0,
        automated_access_permitted=permitted,
    )


def _response(status=200, content=b'{"data": []}', content_type="application/json"):
    response = Mock()
    response.status_code = status
    response.content = content
    response.headers = {"Content-Type": content_type}
    return response


def test_access_is_disabled_by_default_without_making_a_request(monkeypatch):
    get = Mock(side_effect=AssertionError("network call should not happen"))
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(AccessNotPermittedError, match="disabled"):
        acquire_dataset("top-gainers-losers", _config(permitted=False))

    get.assert_not_called()


def test_acquires_non_empty_json_with_explicit_timeout(monkeypatch):
    get = Mock(return_value=_response())
    monkeypatch.setattr(requests, "get", get)

    result = acquire_dataset("top-gainers-losers", _config())

    assert result.dataset_id == "top-gainers-losers"
    assert result.content == b'{"data": []}'
    assert result.content_type == "application/json"
    get.assert_called_once_with(
        "https://www.nseindia.com/market-data/top-gainers-losers",
        timeout=0.25,
        allow_redirects=False,
    )


def test_acquires_csv_payload(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(
            return_value=_response(
                content=b"symbol,value\nABC,10\n",
                content_type="text/csv; charset=utf-8",
            )
        ),
    )

    result = acquire_dataset("upper-band-hitters", _config())

    assert result.content_type == "text/csv"
    assert result.content.startswith(b"symbol,value")


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AccessDeniedError), (403, AccessDeniedError), (429, AccessDeniedError)],
)
def test_access_denied_and_rate_limit_responses_are_not_retried(
    monkeypatch, status, error
):
    get = Mock(return_value=_response(status=status))
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(error):
        acquire_dataset(
            "top-gainers-losers", _config(retries=3), sleep=sleep
        )

    get.assert_called_once()
    sleep.assert_not_called()


def test_transient_timeout_retries_then_succeeds(monkeypatch):
    get = Mock(
        side_effect=[
            requests.Timeout("timed out"),
            _response(content=b'{"ok": true}'),
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)

    result = acquire_dataset("volume-gainers-spurts", _config(), sleep=sleep)

    assert result.content == b'{"ok": true}'
    assert get.call_count == 2
    sleep.assert_called_once_with(0)


@pytest.mark.parametrize(
    "failure",
    [requests.Timeout("timed out"), requests.ConnectionError("offline")],
)
def test_network_failures_stop_after_configured_retry_count(monkeypatch, failure):
    get = Mock(side_effect=failure)
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(AcquisitionError, match="after 3 attempts"):
        acquire_dataset(
            "top-gainers-losers", _config(retries=2), sleep=sleep
        )

    assert get.call_count == 3
    assert sleep.call_count == 2


def test_connection_error_retries_then_succeeds(monkeypatch):
    get = Mock(
        side_effect=[
            requests.ConnectionError("connection failed"),
            _response(content=b'{"ok": true}'),
        ]
    )
    monkeypatch.setattr(requests, "get", get)

    result = acquire_dataset(
        "volume-gainers-spurts", _config(), sleep=Mock()
    )

    assert result.content == b'{"ok": true}'
    assert get.call_count == 2


def test_transient_server_error_retries_to_limit(monkeypatch):
    get = Mock(return_value=_response(status=503))
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(HTTPStatusError, match="after 3 attempts"):
        acquire_dataset(
            "52-week-high-equity-market",
            _config(retries=2),
            sleep=sleep,
        )

    assert get.call_count == 3
    assert sleep.call_count == 2


def test_permanent_http_error_is_not_retried(monkeypatch):
    get = Mock(return_value=_response(status=404))
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(HTTPStatusError, match="HTTP 404"):
        acquire_dataset("top-gainers-losers", _config(), sleep=sleep)

    get.assert_called_once()
    sleep.assert_not_called()


def test_empty_response_is_rejected(monkeypatch):
    monkeypatch.setattr(
        requests, "get", Mock(return_value=_response(content=b" \n"))
    )

    with pytest.raises(EmptyResponseError, match="empty response"):
        acquire_dataset("top-gainers-losers", _config())


@pytest.mark.parametrize(
    "content_type", ["text/html", "application/octet-stream", ""]
)
def test_unexpected_content_type_is_rejected(monkeypatch, content_type):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(return_value=_response(content_type=content_type)),
    )

    with pytest.raises(UnexpectedContentTypeError, match="expected JSON or CSV"):
        acquire_dataset("top-gainers-losers", _config())


def test_unknown_dataset_is_rejected_without_request(monkeypatch):
    get = Mock(side_effect=AssertionError("network call should not happen"))
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(AcquisitionError, match="Unknown dataset"):
        acquire_dataset("unknown-dataset", _config())

    get.assert_not_called()

"""Shared safeguards and fixtures for the automated test suite."""

import pytest
import requests


@pytest.fixture(autouse=True)
def block_unmocked_http(monkeypatch):
    """Fail tests if requests attempts real HTTP instead of using a mock."""
    def reject_request(*args, **kwargs):
        pytest.fail("A test attempted unmocked HTTP access.")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_request)

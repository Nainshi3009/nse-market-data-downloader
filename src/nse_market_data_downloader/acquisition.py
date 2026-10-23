"""Cautious HTTP acquisition for configured NSE datasets."""

from dataclasses import dataclass
import logging
import time
from typing import Callable

import requests

from .config import AppConfig
from .datasets import DATASETS

logger = logging.getLogger(__name__)


class AcquisitionError(RuntimeError):
    """Base class for expected acquisition failures."""


class AccessNotPermittedError(AcquisitionError):
    """Raised when the user has not confirmed permission for automated access."""


class AccessDeniedError(AcquisitionError):
    """Raised when NSE rejects a request or applies a rate limit."""


class HTTPStatusError(AcquisitionError):
    """Raised for an unsuccessful, non-retryable HTTP response."""


class EmptyResponseError(AcquisitionError):
    """Raised when a successful HTTP response contains no usable body."""


class UnexpectedContentTypeError(AcquisitionError):
    """Raised when a response is not explicitly JSON or CSV."""


@dataclass(frozen=True)
class AcquiredPayload:
    """Non-empty response body and its declared media type.

    This object contains unvalidated source data; it is not a validated dataset.
    """

    dataset_id: str
    content: bytes
    content_type: str


def acquire_dataset(
    dataset_id: str,
    config: AppConfig,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> AcquiredPayload:
    """Fetch one configured dataset without bypassing NSE access controls.

    Access is blocked unless configuration explicitly records that automated
    access has been permitted. This function accepts JSON/CSV only, does not
    follow redirects, and never retries 401, 403, or 429 responses.
    """
    if not config.automated_access_permitted:
        raise AccessNotPermittedError(
            "Automated NSE access is disabled. Confirm an explicitly permitted "
            "data-access method before setting "
            "'automated_access_permitted' to true."
        )

    try:
        dataset = DATASETS[dataset_id]
    except KeyError as error:
        supported = ", ".join(DATASETS)
        raise AcquisitionError(
            f"Unknown dataset '{dataset_id}'. Choose one of: {supported}."
        ) from error

    total_attempts = config.max_retries + 1
    for attempt in range(total_attempts):
        attempt_number = attempt + 1
        logger.info(
            "Requesting dataset '%s' (attempt %d of %d).",
            dataset_id,
            attempt_number,
            total_attempts,
        )
        try:
            response = requests.get(
                dataset.page_url,
                timeout=config.request_timeout_seconds,
                allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError) as error:
            if attempt == config.max_retries:
                logger.error(
                    "Request for '%s' failed after %d attempts: %s",
                    dataset_id,
                    attempt_number,
                    type(error).__name__,
                )
                raise AcquisitionError(
                    f"Could not connect to NSE for '{dataset_id}' after "
                    f"{attempt_number} attempts ({type(error).__name__})."
                ) from error
            delay = config.retry_backoff_seconds * (2**attempt)
            logger.warning(
                "Transient network failure for '%s'; retrying in %.2f seconds.",
                dataset_id,
                delay,
            )
            sleep(delay)
            continue
        except requests.RequestException as error:
            logger.error(
                "Request for '%s' failed: %s", dataset_id, type(error).__name__
            )
            raise AcquisitionError(
                f"Request for '{dataset_id}' failed ({type(error).__name__})."
            ) from error

        status = response.status_code
        if status in (401, 403, 429):
            logger.error(
                "NSE rejected or rate-limited '%s' (HTTP %d); not retrying.",
                dataset_id,
                status,
            )
            raise AccessDeniedError(
                f"NSE denied or rate-limited access to '{dataset_id}' "
                f"(HTTP {status}); no retry was attempted."
            )

        if status == 408 or 500 <= status <= 599:
            if attempt < config.max_retries:
                delay = config.retry_backoff_seconds * (2**attempt)
                logger.warning(
                    "Transient HTTP %d for '%s'; retrying in %.2f seconds.",
                    status,
                    dataset_id,
                    delay,
                )
                sleep(delay)
                continue
            logger.error(
                "Request for '%s' ended with HTTP %d after %d attempts.",
                dataset_id,
                status,
                attempt_number,
            )
            raise HTTPStatusError(
                f"NSE returned HTTP {status} for '{dataset_id}' after "
                f"{attempt_number} attempts."
            )

        if not 200 <= status <= 299:
            logger.error("Request for '%s' returned HTTP %d.", dataset_id, status)
            raise HTTPStatusError(
                f"NSE returned HTTP {status} for '{dataset_id}'."
            )

        body = response.content
        if not body or not body.strip():
            logger.error("NSE returned an empty response for '%s'.", dataset_id)
            raise EmptyResponseError(
                f"NSE returned an empty response for '{dataset_id}'."
            )

        media_type = response.headers.get("Content-Type", "").split(";", 1)[0]
        media_type = media_type.strip().lower()
        if not (
            media_type in {"text/csv", "application/csv", "application/json"}
            or media_type.endswith("+json")
        ):
            logger.error(
                "NSE returned unsupported content type '%s' for '%s'.",
                media_type or "<missing>",
                dataset_id,
            )
            raise UnexpectedContentTypeError(
                f"Unsupported content type '{media_type or '<missing>'}' for "
                f"'{dataset_id}'; expected JSON or CSV, not an HTML page."
            )

        logger.info(
            "Received a non-empty %s response for '%s'.",
            media_type,
            dataset_id,
        )
        return AcquiredPayload(
            dataset_id=dataset_id,
            content=body,
            content_type=media_type,
        )

    raise AssertionError("The retry loop ended without returning or raising.")

"""Configuration for timestamped application logging."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Format log records as one structured JSON object per line."""

    _FIELDS = (
        "event",
        "operation",
        "status",
        "dataset_id",
        "record_count",
        "dataset_count",
        "duplicates_removed",
        "file_path",
        "error_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=True)


def configure_logging(logs_dir: str | Path) -> Path:
    """Set up idempotent console and structured file logging.

    Returns the path to the log file. Filesystem errors are raised to the
    caller so the application cannot silently continue without its log.
    """
    directory = Path(logs_dir).expanduser().resolve()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OSError(f"Could not create logs directory '{directory}': {error}") from error

    log_path = directory / "nse-market-data-downloader.log"
    logger = logging.getLogger("nse_market_data_downloader")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError as error:
        raise OSError(f"Could not open application log '{log_path}': {error}") from error
    file_handler.setFormatter(_JsonFormatter())
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(console_handler)
    logger.info(
        "Application logging configured.",
        extra={"event": "logging_configured", "operation": "configure_logging",
               "status": "success", "file_path": str(log_path)},
    )
    return log_path

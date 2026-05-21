import logging
import sys
from pathlib import Path


# Valid log levels
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the application.

    Args:
        log_level: The desired log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                   Defaults to INFO if an invalid value is provided.
    """
    # Validate and normalize log level
    normalized_level = log_level.upper()
    if normalized_level not in VALID_LOG_LEVELS:
        logging.warning(
            "Invalid LOG_LEVEL '%s', falling back to INFO. "
            "Valid levels are: %s",
            log_level,
            ", ".join(sorted(VALID_LOG_LEVELS)),
        )
        normalized_level = "INFO"

    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
    except OSError as exc:
        logging.warning("Could not create log directory '%s': %s", log_dir, exc)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    # Try to add file handler, but continue if it fails
    try:
        file_handler = logging.FileHandler(log_dir / "api.log", encoding="utf-8")
        handlers.append(file_handler)
    except OSError as exc:
        logging.warning("Could not create file handler '%s': %s", log_dir / "api.log", exc)

    logging.basicConfig(level=normalized_level, format=fmt, datefmt=datefmt, handlers=handlers)

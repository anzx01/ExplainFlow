import logging
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "api.log", encoding="utf-8"),
    ]

    logging.basicConfig(level=log_level, format=fmt, datefmt=datefmt, handlers=handlers)

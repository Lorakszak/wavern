"""Centralized logging configuration for Wavern.

Configures a package-level ``wavern`` logger with console and rotating file
handlers.  All other modules obtain child loggers via
``logging.getLogger(__name__)`` and inherit these handlers automatically.
"""

import logging
import logging.handlers
import platform
import sys
from pathlib import Path

from wavern.config import get_config_directory

_SENTINEL: Path | None = Path("__sentinel__")

_LOG_FORMAT_CONSOLE = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_LOG_FORMAT_FILE = (
    "%(asctime)s %(levelname)-7s %(name)s [%(module)s.%(funcName)s:%(lineno)d] %(message)s"
)
_DATEFMT_CONSOLE = "%H:%M:%S"
_DATEFMT_FILE = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 5_242_880  # 5 MB
_BACKUP_COUNT = 3


def setup_logging(
    console_level: str = "WARNING",
    log_file: Path | None = _SENTINEL,
    file_level: str = "DEBUG",
) -> None:
    """Configure the ``wavern`` logger with console and optional file handlers.

    Args:
        console_level: Minimum level for console output (stderr).
        log_file: Path to the rotating log file.  Defaults to
            ``~/.config/wavern/wavern.log``.  Pass ``None`` to disable
            file logging entirely (useful for tests).
        file_level: Minimum level for file output.
    """
    logger = logging.getLogger("wavern")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, console_level.upper(), logging.WARNING))
    console.setFormatter(logging.Formatter(_LOG_FORMAT_CONSOLE, datefmt=_DATEFMT_CONSOLE))
    logger.addHandler(console)

    # File handler
    if log_file is _SENTINEL:
        log_file = get_config_directory() / "wavern.log"

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT_FILE, datefmt=_DATEFMT_FILE))
        logger.addHandler(file_handler)


def log_startup_banner() -> None:
    """Log a diagnostic banner with runtime environment details."""
    logger = logging.getLogger("wavern")

    logger.info("Wavern starting")
    logger.info("Python %s", sys.version)
    logger.info("Platform: %s", platform.platform())

    try:
        from wavern import __version__  # type: ignore[attr-defined]

        logger.info("Wavern version: %s", __version__)
    except (ImportError, AttributeError):
        logger.info("Wavern version: unknown (development)")

    _log_dependency_version(logger, "PySide6")
    _log_dependency_version(logger, "moderngl")
    _log_dependency_version(logger, "numpy")
    _log_dependency_version(logger, "pydantic")


def _log_dependency_version(logger: logging.Logger, package: str) -> None:
    """Log the version of *package*, silently skipping if unavailable."""
    try:
        from importlib.metadata import version

        logger.info("%s %s", package, version(package))
    except Exception:  # noqa: BLE001
        logger.debug("%s version unavailable", package)

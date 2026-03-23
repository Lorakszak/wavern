"""
WHAT THIS TESTS:
- setup_logging creates console and file handlers on the ``wavern`` logger
- Console handler respects the configured level
- File handler always captures DEBUG
- Duplicate calls do not stack handlers (idempotency)
- log_startup_banner emits expected fields
- log_file=None disables file logging
- Custom log_file path creates a file at that location

Does NOT test:
- Actual file rotation (would require writing >5 MB of logs)
"""

import logging
import logging.handlers
from collections.abc import Iterator
from pathlib import Path

import pytest

from wavern.logging_setup import log_startup_banner, setup_logging


@pytest.fixture(autouse=True)
def _clean_wavern_logger() -> Iterator[None]:
    """Remove all handlers from the wavern logger before and after each test."""
    logger = logging.getLogger("wavern")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


class TestSetupLogging:
    def test_creates_two_handlers_with_file(self, tmp_path: Path) -> None:
        setup_logging(log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        assert len(logger.handlers) == 2

    def test_console_handler_type(self, tmp_path: Path) -> None:
        setup_logging(log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        console = logger.handlers[0]
        assert isinstance(console, logging.StreamHandler)
        assert not isinstance(console, logging.FileHandler)

    def test_file_handler_type(self, tmp_path: Path) -> None:
        setup_logging(log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        file_h = logger.handlers[1]
        assert isinstance(file_h, logging.handlers.RotatingFileHandler)

    def test_console_level_respected(self, tmp_path: Path) -> None:
        setup_logging(console_level="ERROR", log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        console = logger.handlers[0]
        assert console.level == logging.ERROR

    def test_file_handler_always_debug(self, tmp_path: Path) -> None:
        setup_logging(console_level="ERROR", log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        file_h = logger.handlers[1]
        assert file_h.level == logging.DEBUG

    def test_idempotent_no_stacking(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        setup_logging(log_file=log_file)
        setup_logging(log_file=log_file)
        logger = logging.getLogger("wavern")
        assert len(logger.handlers) == 2

    def test_no_file_handler_when_none(self) -> None:
        setup_logging(log_file=None)
        logger = logging.getLogger("wavern")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_custom_log_file_created(self, tmp_path: Path) -> None:
        log_file = tmp_path / "custom.log"
        setup_logging(log_file=log_file)
        logger = logging.getLogger("wavern")
        logger.info("hello")
        assert log_file.exists()
        content = log_file.read_text()
        assert "hello" in content

    def test_propagate_disabled(self, tmp_path: Path) -> None:
        setup_logging(log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        assert logger.propagate is False

    def test_logger_level_is_debug(self, tmp_path: Path) -> None:
        setup_logging(log_file=tmp_path / "test.log")
        logger = logging.getLogger("wavern")
        assert logger.level == logging.DEBUG

    def test_file_handler_rotating_config(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        setup_logging(log_file=log_file)
        logger = logging.getLogger("wavern")
        file_h = logger.handlers[1]
        assert isinstance(file_h, logging.handlers.RotatingFileHandler)
        assert file_h.maxBytes == 5_242_880
        assert file_h.backupCount == 3


class TestStartupBanner:
    """Banner tests use the file handler to capture output (caplog doesn't
    work with propagate=False)."""

    def test_logs_python_version(self, tmp_path: Path) -> None:
        log_file = tmp_path / "banner.log"
        setup_logging(console_level="DEBUG", log_file=log_file)
        log_startup_banner()
        content = log_file.read_text()
        assert "Python" in content

    def test_logs_platform(self, tmp_path: Path) -> None:
        log_file = tmp_path / "banner.log"
        setup_logging(console_level="DEBUG", log_file=log_file)
        log_startup_banner()
        content = log_file.read_text()
        assert "Platform" in content

    def test_logs_wavern_starting(self, tmp_path: Path) -> None:
        log_file = tmp_path / "banner.log"
        setup_logging(console_level="DEBUG", log_file=log_file)
        log_startup_banner()
        content = log_file.read_text()
        assert "Wavern starting" in content

    def test_logs_dependency_versions(self, tmp_path: Path) -> None:
        log_file = tmp_path / "banner.log"
        setup_logging(console_level="DEBUG", log_file=log_file)
        log_startup_banner()
        content = log_file.read_text()
        assert "numpy" in content
        assert "PySide6" in content

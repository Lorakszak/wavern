"""Shared fixtures for GUI tests."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp: QApplication) -> None:
    """Ensure a QApplication exists for all GUI tests via pytest-qt."""

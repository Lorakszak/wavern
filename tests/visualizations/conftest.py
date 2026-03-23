"""Shared fixtures for visualization tests."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp: QApplication) -> None:
    """Ensure a QApplication exists for visualization tests that create widgets."""

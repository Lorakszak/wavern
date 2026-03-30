"""Tests for TransportBar overlay styling.

WHAT THIS TESTS
- set_overlay_style toggles the semi-transparent background
Does NOT test: playback signals, seek behavior (covered by integration tests)
"""

import pytest
from PySide6.QtWidgets import QApplication

from wavern.gui.transport_bar import TransportBar


@pytest.fixture(scope="module")
def _app():
    """Ensure QApplication exists for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def transport(_app):
    return TransportBar()


def test_overlay_style_enabled(transport: TransportBar) -> None:
    """Enabling overlay style sets a semi-transparent background."""
    transport.set_overlay_style(True)
    sheet = transport.styleSheet()
    assert "rgba" in sheet
    assert "background" in sheet.lower()


def test_overlay_style_disabled_restores(transport: TransportBar) -> None:
    """Disabling overlay style restores the original stylesheet."""
    original = transport.styleSheet()
    transport.set_overlay_style(True)
    transport.set_overlay_style(False)
    assert transport.styleSheet() == original


def test_overlay_style_idempotent(transport: TransportBar) -> None:
    """Calling set_overlay_style(True) twice doesn't corrupt saved style."""
    original = transport.styleSheet()
    transport.set_overlay_style(True)
    transport.set_overlay_style(True)
    transport.set_overlay_style(False)
    assert transport.styleSheet() == original

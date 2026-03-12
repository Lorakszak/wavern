"""Shared help-button utility for settings panels."""

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton, QToolTip

HELP_BUTTON_STYLE = (
    "QPushButton { border-radius: 10px; border: 1px solid #555; "
    "background: #333; color: #aaa; font-weight: bold; font-size: 11px; }"
    "QPushButton:hover { background: #555; color: #fff; }"
)


def make_help_button(tooltip: str) -> QPushButton:
    """Create a small circular '?' button that shows its tooltip on click."""
    btn = QPushButton("?")
    btn.setFixedSize(20, 20)
    btn.setStyleSheet(HELP_BUTTON_STYLE)
    btn.setToolTip(tooltip)
    btn.clicked.connect(lambda: QToolTip.showText(QCursor.pos(), tooltip, btn))
    return btn

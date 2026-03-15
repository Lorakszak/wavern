"""Shared help-button utility for settings panels."""

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton, QToolTip


def make_help_button(tooltip: str) -> QPushButton:
    """Create a small circular '?' button that shows its tooltip on click."""
    btn = QPushButton("?")
    btn.setObjectName("HelpButton")
    btn.setFixedSize(20, 20)
    btn.setToolTip(tooltip)
    btn.clicked.connect(lambda: QToolTip.showText(QCursor.pos(), tooltip, btn))
    return btn

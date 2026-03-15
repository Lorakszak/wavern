"""NoScrollComboBox — QComboBox that ignores wheel events unless Ctrl is held."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QWidget


class NoScrollComboBox(QComboBox):
    """QComboBox that ignores wheel events to prevent accidental changes while scrolling.

    Ctrl+scroll is still allowed as a deliberate interaction.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
        else:
            event.ignore()

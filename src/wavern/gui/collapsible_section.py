"""Reusable collapsible section widget with clickable header."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """A section with a clickable header that toggles content visibility."""

    def __init__(self, title: str, expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self._header = QPushButton()
        self._header.setObjectName("CollapsibleHeader")
        self._header.setFlat(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        # Content container
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 4, 0, 4)
        layout.addWidget(self._container)

        self._update_header()
        self._container.setVisible(self._expanded)

    def set_content(self, widget: QWidget) -> None:
        """Set the content widget inside this section."""
        # Clear existing content
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._container_layout.addWidget(widget)

    def set_expanded(self, expanded: bool) -> None:
        """Set the expanded/collapsed state."""
        self._expanded = expanded
        self._container.setVisible(self._expanded)
        self._update_header()

    def is_expanded(self) -> bool:
        """Return whether the section is currently expanded."""
        return self._expanded

    @property
    def title(self) -> str:
        return self._title

    def _toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _update_header(self) -> None:
        chevron = "\u25BC" if self._expanded else "\u25B6"
        self._header.setText(f"{chevron}  {self._title}")

"""Sidebar widget — tabbed panel container with optional vertical split."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class _TabPane(QWidget):
    """Single tab-bar + stacked-widget pair used inside a SidebarWidget."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)

        self._stack = QStackedWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._stack)

        layout.addWidget(scroll, stretch=1)

        self._tabs: list[dict[str, Any]] = []

    @property
    def tab_bar(self) -> QTabBar:
        return self._tab_bar

    def add_tab(self, name: str, widget: QWidget) -> int:
        """Add a tab and return its index."""
        idx = self._tab_bar.addTab(name)
        self._stack.addWidget(widget)
        self._tabs.append({"name": name, "widget": widget})
        return idx

    def tab_count(self) -> int:
        return self._tab_bar.count()

    def current_index(self) -> int:
        return self._tab_bar.currentIndex()

    def set_current_index(self, index: int) -> None:
        self._tab_bar.setCurrentIndex(index)

    def widget_at(self, index: int) -> QWidget | None:
        if 0 <= index < len(self._tabs):
            return self._tabs[index]["widget"]
        return None

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self.tab_changed.emit(index)


class SidebarWidget(QWidget):
    """Tabbed sidebar with optional vertical split into two independent panes."""

    tab_changed = Signal(int)  # emitted when the active (upper) tab changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._split = False

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Upper pane (always visible)
        self._upper = _TabPane()
        self._upper.tab_changed.connect(self.tab_changed.emit)

        # Lower pane (only visible when split)
        self._lower = _TabPane()

        # Splitter holds both panes
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._upper)
        self._splitter.addWidget(self._lower)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        self._lower.setVisible(False)

        self._layout.addWidget(self._splitter)

    @property
    def upper(self) -> _TabPane:
        return self._upper

    @property
    def lower(self) -> _TabPane:
        return self._lower

    def add_tab(self, name: str, widget: QWidget) -> int:
        """Add a tab to the upper pane."""
        return self._upper.add_tab(name, widget)

    def add_lower_tab(self, name: str, widget: QWidget) -> int:
        """Add a tab to the lower pane (visible only when split)."""
        return self._lower.add_tab(name, widget)

    def tab_count(self) -> int:
        return self._upper.tab_count()

    def current_index(self) -> int:
        return self._upper.current_index()

    def set_current_index(self, index: int) -> None:
        self._upper.set_current_index(index)

    @property
    def is_split(self) -> bool:
        return self._split

    def set_split(self, split: bool) -> None:
        """Toggle split mode — shows/hides the lower pane."""
        self._split = split
        self._lower.setVisible(split)

    def toggle_split(self) -> None:
        self.set_split(not self._split)

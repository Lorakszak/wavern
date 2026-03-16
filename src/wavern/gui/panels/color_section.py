"""Color palette editor section for the visual settings panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.presets.schema import Preset


class ColorSection(QWidget):
    """Editable color palette widget with add/remove/reorder controls."""

    colors_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._color_buttons: list[QPushButton] = []
        self._preset: Preset | None = None
        self._rebuilding = False

    def build(self, preset: Preset) -> None:
        """Clear and rebuild the color palette rows from the preset.

        Args:
            preset: The active preset whose color_palette to display and mutate.
        """
        self._rebuilding = True
        self._preset = preset
        self._color_buttons.clear()

        # Remove all existing child widgets and sub-layouts.
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

        for i, color_hex in enumerate(preset.color_palette):
            row = QHBoxLayout()

            up_btn = QPushButton("\u25B2")
            up_btn.setObjectName("ColorControlBtn")
            up_btn.setFixedSize(24, 24)
            up_btn.setEnabled(i > 0)
            up_btn.clicked.connect(lambda _, idx=i: self._on_move_color_up(idx))
            row.addWidget(up_btn)

            down_btn = QPushButton("\u25BC")
            down_btn.setObjectName("ColorControlBtn")
            down_btn.setFixedSize(24, 24)
            down_btn.setEnabled(i < len(preset.color_palette) - 1)
            down_btn.clicked.connect(
                lambda _, idx=i: self._on_move_color_down(idx)
            )
            row.addWidget(down_btn)

            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(
                f"background-color: {color_hex}; border: 1px solid #555;"
            )
            btn.clicked.connect(lambda _, idx=i: self._on_color_clicked(idx))
            row.addWidget(btn)

            label = QLabel(color_hex)
            row.addWidget(label)

            remove_btn = QPushButton("x")
            remove_btn.setObjectName("ColorControlBtn")
            remove_btn.setFixedSize(24, 24)
            remove_btn.clicked.connect(
                lambda _, idx=i: self._on_remove_color(idx)
            )
            row.addWidget(remove_btn)

            # Wrap the row layout in a container widget so it can be managed
            # by the top-level QVBoxLayout.
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._layout.addWidget(row_widget)
            self._color_buttons.append(btn)

        add_btn = QPushButton("+ Add Color")
        add_btn.clicked.connect(self._on_add_color)
        self._layout.addWidget(add_btn)

        self._rebuilding = False

    def update_values(self, color_palette: list[str]) -> None:
        """Update button stylesheets in-place without rebuilding.

        Args:
            color_palette: The current list of hex color strings.
        """
        for i, btn in enumerate(self._color_buttons):
            if i < len(color_palette):
                btn.setStyleSheet(
                    f"background-color: {color_palette[i]};"
                    " border: 1px solid #555;"
                )

    def _on_color_clicked(self, index: int) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.color_palette[index])
        color = QColorDialog.getColor(current, self, "Pick Color")
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.color_palette[index] = hex_color
            self._color_buttons[index].setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self.colors_changed.emit()

    def _on_add_color(self) -> None:
        if self._preset is None:
            return
        color = QColorDialog.getColor(parent=self, title="Add Color")
        if color.isValid():
            self._preset.color_palette.append(color.name().upper())
            self.build(self._preset)
            self.colors_changed.emit()

    def _on_remove_color(self, index: int) -> None:
        if self._preset is None or len(self._preset.color_palette) <= 1:
            return
        self._preset.color_palette.pop(index)
        self.build(self._preset)
        self.colors_changed.emit()

    def _on_move_color_up(self, index: int) -> None:
        if self._preset is None or index <= 0:
            return
        palette = self._preset.color_palette
        palette[index], palette[index - 1] = (
            palette[index - 1],
            palette[index],
        )
        self.build(self._preset)
        self.colors_changed.emit()

    def _on_move_color_down(self, index: int) -> None:
        if self._preset is None or index >= len(self._preset.color_palette) - 1:
            return
        palette = self._preset.color_palette
        palette[index], palette[index + 1] = (
            palette[index + 1],
            palette[index],
        )
        self.build(self._preset)
        self.colors_changed.emit()


def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    """Recursively remove all items from a layout and delete their widgets."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())

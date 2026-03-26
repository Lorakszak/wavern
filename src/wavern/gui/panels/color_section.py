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
    """Editable color palette widget scoped to a single visualization layer."""

    colors_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._color_buttons: list[QPushButton] = []
        self._preset: Preset | None = None
        self._rebuilding = False
        self._layer_index: int = 0

    def build_for_layer(self, preset: Preset, layer_index: int) -> None:
        """Build color section for a specific layer's colors.

        Args:
            preset: The active preset.
            layer_index: Index into preset.layers for the target layer.
        """
        self._layer_index = layer_index
        self._preset = preset
        self._rebuilding = True
        self._color_buttons.clear()

        while self._layout.count():
            item = self._layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None and isinstance(sub, (QVBoxLayout, QHBoxLayout)):
                    _clear_layout(sub)

        palette = preset.layers[layer_index].colors
        for i, color_hex in enumerate(palette):
            row = QHBoxLayout()

            up_btn = QPushButton("\u25b2")
            up_btn.setObjectName("ColorControlBtn")
            up_btn.setFixedSize(24, 24)
            up_btn.setEnabled(i > 0)
            up_btn.clicked.connect(lambda _, idx=i: self._on_move_color_up(idx))
            row.addWidget(up_btn)

            down_btn = QPushButton("\u25bc")
            down_btn.setObjectName("ColorControlBtn")
            down_btn.setFixedSize(24, 24)
            down_btn.setEnabled(i < len(palette) - 1)
            down_btn.clicked.connect(lambda _, idx=i: self._on_move_color_down(idx))
            row.addWidget(down_btn)

            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(f"background-color: {color_hex}; border: 1px solid #555;")
            btn.clicked.connect(lambda _, idx=i: self._on_color_clicked(idx))
            row.addWidget(btn)

            label = QLabel(color_hex)
            row.addWidget(label)

            remove_btn = QPushButton("x")
            remove_btn.setObjectName("ColorControlBtn")
            remove_btn.setFixedSize(24, 24)
            remove_btn.clicked.connect(lambda _, idx=i: self._on_remove_color(idx))
            row.addWidget(remove_btn)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self._layout.addWidget(row_widget)
            self._color_buttons.append(btn)

        add_btn = QPushButton("+ Add Color")
        add_btn.clicked.connect(self._on_add_color)
        self._layout.addWidget(add_btn)

        self._rebuilding = False

    def _layer_colors(self) -> list[str] | None:
        """Return the current layer's colors list for mutation."""
        if self._preset is None:
            return None
        return self._preset.layers[self._layer_index].colors

    def _on_color_clicked(self, index: int) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        palette = self._layer_colors()
        if palette is None:
            return
        current = QColor(palette[index])
        color = QColorDialog.getColor(current, self, "Pick Color")
        if color.isValid():
            hex_color = color.name().upper()
            palette[index] = hex_color
            self._color_buttons[index].setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self.colors_changed.emit()

    def _on_add_color(self) -> None:
        if self._preset is None:
            return
        color = QColorDialog.getColor(parent=self, title="Add Color")
        if color.isValid():
            palette = self._layer_colors()
            if palette is None:
                return
            palette.append(color.name().upper())
            self.build_for_layer(self._preset, self._layer_index)
            self.colors_changed.emit()

    def _on_remove_color(self, index: int) -> None:
        if self._preset is None:
            return
        palette = self._layer_colors()
        if palette is None or len(palette) <= 1:
            return
        palette.pop(index)
        self.build_for_layer(self._preset, self._layer_index)
        self.colors_changed.emit()

    def _on_move_color_up(self, index: int) -> None:
        if self._preset is None or index <= 0:
            return
        palette = self._layer_colors()
        if palette is None:
            return
        palette[index], palette[index - 1] = palette[index - 1], palette[index]
        self.build_for_layer(self._preset, self._layer_index)
        self.colors_changed.emit()

    def _on_move_color_down(self, index: int) -> None:
        if self._preset is None:
            return
        palette = self._layer_colors()
        if palette is None or index >= len(palette) - 1:
            return
        palette[index], palette[index + 1] = palette[index + 1], palette[index]
        self.build_for_layer(self._preset, self._layer_index)
        self.colors_changed.emit()


def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    """Recursively remove all items from a layout and delete their widgets."""
    while layout.count():
        item = layout.takeAt(0)
        assert item is not None
        w = item.widget()
        if w is not None:
            w.deleteLater()
        else:
            sub = item.layout()
            if sub is not None and isinstance(sub, (QVBoxLayout, QHBoxLayout)):
                _clear_layout(sub)

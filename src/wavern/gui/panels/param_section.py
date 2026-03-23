"""Extracted widget section for visualization-specific parameter controls."""

import logging
import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class ParamSection(QWidget):
    """Builds and manages per-visualization parameter widgets from PARAM_SCHEMA."""

    params_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widgets: dict[str, QWidget] = {}
        self._params_layout = QFormLayout(self)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._rebuilding: bool = False
        self._current_viz_type: str | None = None
        self._current_params: dict[str, Any] = {}

    @property
    def widgets(self) -> dict[str, QWidget]:
        return self._widgets

    def build(
        self, viz_type: str, current_params: dict[str, Any],
    ) -> None:
        self._rebuilding = True
        self._current_viz_type = viz_type
        self._current_params = dict(current_params)
        self._widgets.clear()

        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    while sub.count():
                        sub_item = sub.takeAt(0)
                        assert sub_item is not None
                        sw = sub_item.widget()
                        if sw is not None:
                            sw.deleteLater()

        registry = VisualizationRegistry()
        try:
            viz_class = registry.get(viz_type)
        except KeyError:
            self._rebuilding = False
            return

        for param_name, schema in viz_class.PARAM_SCHEMA.items():
            param_type = schema.get("type", "float")
            label = schema.get("label", param_name)
            default = schema.get("default")
            current_val = current_params.get(param_name, default)

            widget: QWidget

            if param_type == "int":
                p_min = schema.get("min", 0)
                p_max = schema.get("max", 9999)
                description = schema.get("description", "")
                widget = DragSpinBox(
                    minimum=p_min,
                    maximum=p_max,
                    step=1,
                    decimals=0,
                    description=description,
                    default_value=float(default) if default is not None else None,
                )
                widget.setValue(int(current_val or 0))
                widget.valueChanged.connect(
                    lambda v, n=param_name: self._on_param_changed(n, int(v))
                )

            elif param_type == "float":
                p_min = schema.get("min", 0.0)
                p_max = schema.get("max", 100.0)
                description = schema.get("description", "")
                widget = DragSpinBox(
                    minimum=p_min,
                    maximum=p_max,
                    step=0.01,
                    decimals=3,
                    description=description,
                    default_value=float(default) if default is not None else None,
                )
                widget.setValue(float(current_val or 0.0))
                widget.valueChanged.connect(
                    lambda v, n=param_name: self._on_param_changed(n, v)
                )

            elif param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(current_val))
                widget.toggled.connect(
                    lambda v, n=param_name: self._on_param_changed(n, bool(v))
                )

            elif param_type == "color":
                widget = QPushButton()
                widget.setFixedSize(30, 30)
                hex_val = str(current_val or default or "#000000")
                widget.setStyleSheet(
                    f"background-color: {hex_val}; border: 1px solid #555;"
                )
                widget.clicked.connect(
                    lambda _, n=param_name, w=widget: (
                        self._on_color_param_clicked(n, w)
                    )
                )

            elif param_type == "file":
                widget = QWidget()
                file_layout = QHBoxLayout(widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                file_label = QLabel(
                    self._elide_path(str(current_val))
                    if current_val
                    else "No image"
                )
                file_label.setFixedWidth(120)
                file_layout.addWidget(file_label, stretch=1)

                file_filter = schema.get("file_filter", "All Files (*)")
                browse_btn = QPushButton("Browse...")
                browse_btn.clicked.connect(
                    lambda _, n=param_name, lbl=file_label, ff=file_filter: (
                        self._on_file_param_browse(n, lbl, ff)
                    )
                )
                file_layout.addWidget(browse_btn)

                clear_btn = QPushButton("\u00d7")
                clear_btn.setFixedSize(24, 24)
                clear_btn.clicked.connect(
                    lambda _, n=param_name, lbl=file_label: (
                        self._on_file_param_clear(n, lbl)
                    )
                )
                file_layout.addWidget(clear_btn)

            elif param_type == "choice":
                widget = NoScrollComboBox()
                for choice in schema.get("choices", []):
                    widget.addItem(str(choice), choice)
                if current_val is not None:
                    idx = widget.findData(current_val)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                widget.currentIndexChanged.connect(
                    lambda _, n=param_name, w=widget: self._on_param_changed(
                        n, w.currentData()
                    )
                )

            else:
                continue

            self._widgets[param_name] = widget
            if schema.get("disabled", False):
                widget.setEnabled(False)
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                lambda pos, n=param_name, w=widget: (
                    self._show_param_context_menu(n, w, pos)
                )
            )
            self._params_layout.addRow(f"{label}:", widget)

        self._rebuilding = False

    def update_values(self, params: dict[str, Any]) -> None:
        self._rebuilding = True
        self._current_params = dict(params)
        for param_name, widget in self._widgets.items():
            val = params.get(param_name)
            if val is None:
                continue
            if isinstance(widget, DragSpinBox):
                widget.blockSignals(True)
                widget.setValue(val)
                widget.blockSignals(False)
            elif isinstance(widget, QCheckBox):
                widget.blockSignals(True)
                widget.setChecked(bool(val))
                widget.blockSignals(False)
            elif isinstance(widget, NoScrollComboBox):
                widget.blockSignals(True)
                ci = widget.findData(val)
                if ci >= 0:
                    widget.setCurrentIndex(ci)
                widget.blockSignals(False)
            elif isinstance(widget, QPushButton):
                widget.setStyleSheet(
                    f"background-color: {val}; border: 1px solid #555;"
                )
        self._rebuilding = False

    def _on_param_changed(self, name: str, value: Any) -> None:
        if self._rebuilding:
            return
        self._current_params[name] = value
        self.params_changed.emit(name, value)

    def _show_param_context_menu(
        self, param_name: str, widget: QWidget, pos: Any,
    ) -> None:
        viz_type = self._current_viz_type
        if viz_type is None:
            return
        registry = VisualizationRegistry()
        try:
            viz_class = registry.get(viz_type)
        except KeyError:
            return
        schema = viz_class.PARAM_SCHEMA.get(param_name)
        if schema is None or "default" not in schema:
            return

        menu = QMenu(self)
        reset_action = QAction(
            f"Reset to default ({schema['default']})", self,
        )
        default_val = schema["default"]

        def _do_reset() -> None:
            param_type = schema.get("type", "float")
            if param_type in ("int", "float") and isinstance(
                widget, DragSpinBox,
            ):
                widget.setValue(default_val)
            elif param_type == "bool" and isinstance(widget, QCheckBox):
                widget.setChecked(bool(default_val))
            elif param_type == "choice" and isinstance(
                widget, NoScrollComboBox,
            ):
                idx = widget.findData(default_val)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif param_type == "color" and isinstance(widget, QPushButton):
                widget.setStyleSheet(
                    f"background-color: {default_val};"
                    " border: 1px solid #555;"
                )
                self._on_param_changed(param_name, default_val)

        reset_action.triggered.connect(_do_reset)
        menu.addAction(reset_action)
        menu.exec(widget.mapToGlobal(pos))

    def _on_color_param_clicked(
        self, param_name: str, button: QPushButton,
    ) -> None:
        from PySide6.QtGui import QColor

        current_hex = self._current_params.get(param_name, "#000000")
        color = QColorDialog.getColor(
            QColor(str(current_hex)), self, "Pick Color",
        )
        if color.isValid():
            hex_color = color.name().upper()
            button.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._on_param_changed(param_name, hex_color)

    def _on_file_param_browse(
        self, param_name: str, label: QLabel, file_filter: str,
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", file_filter,
        )
        if path:
            label.setText(self._elide_path(path))
            self._on_param_changed(param_name, path)

    def _on_file_param_clear(
        self, param_name: str, label: QLabel,
    ) -> None:
        label.setText("No image")
        self._on_param_changed(param_name, "")

    @staticmethod
    def _elide_path(path: str, max_len: int = 20) -> str:
        if len(path) <= max_len:
            return path
        return "..." + os.sep + os.path.basename(path)

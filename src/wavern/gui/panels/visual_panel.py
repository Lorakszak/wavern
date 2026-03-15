"""Visual panel — visualization type selector, parameter widgets, colors, background."""

import logging
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
    QVBoxLayout,
    QWidget,
)

from wavern.gui.no_scroll_combo import NoScrollComboBox

from wavern.gui.background_picker import open_background_image
from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.presets.schema import BackgroundConfig, ColorStop, Preset, VisualizationParams
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class VisualPanel(QWidget):
    """Visualization type, parameters, colors, and background settings."""

    params_changed = Signal(object)  # updated Preset

    def __init__(
        self,
        parent: QWidget | None = None,
        viz_memory: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._widgets: dict[str, QWidget] = {}
        self._color_buttons: list[QPushButton] = []
        self._rebuilding: bool = False
        self._section_states: dict[str, bool] = {}
        self._viz_memory: dict[str, dict[str, Any]] = viz_memory if viz_memory is not None else {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = layout

    def set_preset(self, preset: Preset) -> None:
        """Rebuild the visual panel for the given preset."""
        self._preset = preset
        self._widgets.clear()
        self._color_buttons.clear()
        self._rebuilding = True

        self._save_section_states()

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # --- Visualization (type + parameters) ---
        self._viz_section = CollapsibleSection("Visualization")
        viz_content = QWidget()
        viz_layout = QVBoxLayout(viz_content)
        viz_layout.setContentsMargins(4, 0, 4, 0)

        type_form = QFormLayout()
        registry = VisualizationRegistry()
        self._viz_combo = NoScrollComboBox()
        self._viz_combo.blockSignals(True)
        for info in registry.list_all():
            self._viz_combo.addItem(info["display_name"], info["name"])

        current_type = preset.visualization.visualization_type
        for i in range(self._viz_combo.count()):
            if self._viz_combo.itemData(i) == current_type:
                self._viz_combo.setCurrentIndex(i)
                break
        self._viz_combo.blockSignals(False)
        self._viz_combo.currentIndexChanged.connect(self._on_viz_type_changed)

        type_row = QHBoxLayout()
        type_row.addWidget(self._viz_combo, stretch=1)
        self._reset_all_btn = QPushButton("Reset All")
        self._reset_all_btn.setFixedWidth(90)
        self._reset_all_btn.clicked.connect(self._on_reset_all_params)
        type_row.addWidget(self._reset_all_btn)
        type_form.addRow("Type:", type_row)
        viz_layout.addLayout(type_form)

        self._params_container = QWidget()
        self._params_layout = QFormLayout(self._params_container)
        self._params_layout.setContentsMargins(0, 4, 0, 0)
        self._build_param_widgets(current_type, preset.visualization.params)
        viz_layout.addWidget(self._params_container)

        self._viz_section.set_content(viz_content)
        self._content_layout.addWidget(self._viz_section)

        # --- Colors ---
        self._color_section = CollapsibleSection("Colors")
        self._build_color_section(preset)
        self._content_layout.addWidget(self._color_section)

        # --- Background ---
        self._bg_section = CollapsibleSection("Background")
        self._build_background_section(preset)
        self._content_layout.addWidget(self._bg_section)

        self._restore_section_states()
        self._rebuilding = False

    def update_values(self, preset: Preset) -> None:
        """Update widget values in-place without rebuilding.

        Falls back to set_preset() when structural changes occur (viz type,
        bg type, color count, or gradient stop count changed).
        """
        if not hasattr(self, "_viz_combo") or self._preset is None:
            self.set_preset(preset)
            return

        old = self._preset

        # Detect structural changes that require full rebuild
        if (preset.visualization.visualization_type
                != old.visualization.visualization_type):
            self.set_preset(preset)
            return
        if preset.background.type != old.background.type:
            self.set_preset(preset)
            return
        if len(preset.color_palette) != len(old.color_palette):
            self.set_preset(preset)
            return
        if (preset.background.type == "gradient"
                and len(preset.background.gradient_stops)
                != len(old.background.gradient_stops)):
            self.set_preset(preset)
            return

        self._preset = preset
        self._rebuilding = True

        # Update viz combo selection
        self._viz_combo.blockSignals(True)
        idx = self._viz_combo.findData(preset.visualization.visualization_type)
        if idx >= 0:
            self._viz_combo.setCurrentIndex(idx)
        self._viz_combo.blockSignals(False)

        # Update parameter widgets
        for param_name, widget in self._widgets.items():
            val = preset.visualization.params.get(param_name)
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
                # Color param button — just update stylesheet
                widget.setStyleSheet(
                    f"background-color: {val}; border: 1px solid #555;"
                )

        # Update color palette buttons
        for i, btn in enumerate(self._color_buttons):
            if i < len(preset.color_palette):
                btn.setStyleSheet(
                    f"background-color: {preset.color_palette[i]}; border: 1px solid #555;"
                )

        # Update background sub-widgets
        bg = preset.background
        if bg.type == "solid" and hasattr(self, "_bg_color_btn"):
            self._bg_color_btn.setStyleSheet(
                f"background-color: {bg.color}; border: 1px solid #555;"
            )
        elif bg.type == "image" and hasattr(self, "_bg_image_label"):
            self._bg_image_label.setText(bg.image_path or "No image selected")
        elif bg.type == "gradient" and hasattr(self, "_gradient_stop_widgets"):
            for i, stop_widgets in enumerate(self._gradient_stop_widgets):
                if i < len(bg.gradient_stops):
                    stop = bg.gradient_stops[i]
                    stop_widgets["color_btn"].setStyleSheet(
                        f"background-color: {stop.color}; border: 1px solid #555;"
                    )
                    pos_spin = stop_widgets["pos_spin"]
                    pos_spin.blockSignals(True)
                    pos_spin.setValue(stop.position)
                    pos_spin.blockSignals(False)

        self._rebuilding = False

    def set_viz_by_index(self, index: int) -> None:
        """Switch visualization type by combo index (0-based)."""
        if self._preset is None or index >= self._viz_combo.count():
            return
        self._viz_combo.setCurrentIndex(index)

    # -- Section state persistence --

    def _save_section_states(self) -> None:
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
        }
        for name, attr in attr_map.items():
            if hasattr(self, attr):
                self._section_states[name] = getattr(self, attr).is_expanded()

    def _restore_section_states(self) -> None:
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
        }
        for name, expanded in self._section_states.items():
            attr = attr_map.get(name)
            if attr and hasattr(self, attr):
                getattr(self, attr).set_expanded(expanded)

    # -- Parameter widgets --

    def _build_param_widgets(self, viz_type: str, current_params: dict[str, Any]) -> None:
        """Build parameter widgets from the visualization's PARAM_SCHEMA."""
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        registry = VisualizationRegistry()
        try:
            viz_class = registry.get(viz_type)
        except KeyError:
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
                    minimum=p_min, maximum=p_max, step=1,
                    decimals=0, description=description,
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
                    minimum=p_min, maximum=p_max, step=0.01,
                    decimals=3, description=description,
                    default_value=float(default) if default is not None else None,
                )
                widget.setValue(float(current_val or 0.0))
                widget.valueChanged.connect(
                    lambda v, n=param_name: self._on_param_changed(n, v)
                )

            elif param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(current_val))
                widget.stateChanged.connect(
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
                    lambda _, n=param_name, w=widget: self._on_color_param_clicked(n, w)
                )

            elif param_type == "file":
                widget = QWidget()
                file_layout = QHBoxLayout(widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                file_label = QLabel(
                    self._elide_path(str(current_val)) if current_val else "No image"
                )
                file_label.setFixedWidth(120)
                file_layout.addWidget(file_label, stretch=1)

                file_filter = schema.get("file_filter", "All Files (*)")
                browse_btn = QPushButton("Browse...")
                browse_btn.clicked.connect(
                    lambda _, n=param_name, lbl=file_label, ff=file_filter:
                        self._on_file_param_browse(n, lbl, ff)
                )
                file_layout.addWidget(browse_btn)

                clear_btn = QPushButton("\u00d7")
                clear_btn.setFixedSize(24, 24)
                clear_btn.clicked.connect(
                    lambda _, n=param_name, lbl=file_label:
                        self._on_file_param_clear(n, lbl)
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
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                lambda pos, n=param_name, w=widget: self._show_param_context_menu(n, w, pos)
            )
            self._params_layout.addRow(f"{label}:", widget)

    # -- Color palette --

    def _build_color_section(self, preset: Preset) -> None:
        color_content = QWidget()
        color_layout = QVBoxLayout(color_content)
        color_layout.setContentsMargins(4, 0, 4, 0)

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

            color_layout.addLayout(row)
            self._color_buttons.append(btn)

        add_btn = QPushButton("+ Add Color")
        add_btn.clicked.connect(self._on_add_color)
        color_layout.addWidget(add_btn)

        self._color_section.set_content(color_content)

    # -- Background --

    def _build_background_section(self, preset: Preset) -> None:
        bg_content = QWidget()
        self._bg_layout = QFormLayout(bg_content)
        self._bg_layout.setContentsMargins(4, 0, 4, 0)

        self._bg_type_combo = NoScrollComboBox()
        self._bg_type_combo.blockSignals(True)
        for bg_type in ["solid", "none", "image", "gradient"]:
            self._bg_type_combo.addItem(bg_type, bg_type)
        idx = self._bg_type_combo.findData(preset.background.type)
        if idx >= 0:
            self._bg_type_combo.setCurrentIndex(idx)
        self._bg_type_combo.blockSignals(False)
        self._bg_type_combo.currentIndexChanged.connect(self._on_bg_changed)
        self._bg_layout.addRow("Type:", self._bg_type_combo)

        self._bg_type_container = QWidget()
        self._bg_type_container_layout = QVBoxLayout(self._bg_type_container)
        self._bg_type_container_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.addRow(self._bg_type_container)

        self._rebuild_bg_type_widgets(preset.background)
        self._bg_section.set_content(bg_content)

    def _rebuild_bg_type_widgets(self, bg: BackgroundConfig) -> None:
        layout = self._bg_type_container_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        if bg.type == "solid":
            self._bg_color_btn = QPushButton()
            self._bg_color_btn.setFixedSize(30, 30)
            self._bg_color_btn.setStyleSheet(
                f"background-color: {bg.color}; border: 1px solid #555;"
            )
            self._bg_color_btn.clicked.connect(self._on_bg_color_clicked)
            row = QHBoxLayout()
            row.addWidget(QLabel("Color:"))
            row.addWidget(self._bg_color_btn)
            row.addStretch()
            layout.addLayout(row)

        elif bg.type == "image":
            self._bg_image_label = QLabel(bg.image_path or "No image selected")
            self._bg_image_label.setWordWrap(True)
            pick_btn = QPushButton("Browse...")
            pick_btn.clicked.connect(self._on_bg_image_pick)
            row = QHBoxLayout()
            row.addWidget(self._bg_image_label, stretch=1)
            row.addWidget(pick_btn)
            layout.addLayout(row)

        elif bg.type == "gradient":
            self._gradient_stop_widgets: list[dict[str, QWidget]] = []
            for i, stop in enumerate(bg.gradient_stops):
                self._add_gradient_stop_row(layout, i, stop)
            add_btn = QPushButton("+ Add Stop")
            add_btn.clicked.connect(self._on_add_gradient_stop)
            layout.addWidget(add_btn)

    def _add_gradient_stop_row(
        self, layout: QVBoxLayout, index: int, stop: ColorStop
    ) -> None:
        row = QHBoxLayout()

        color_btn = QPushButton()
        color_btn.setFixedSize(30, 30)
        color_btn.setStyleSheet(
            f"background-color: {stop.color}; border: 1px solid #555;"
        )
        color_btn.clicked.connect(lambda _, idx=index: self._on_gradient_color_clicked(idx))
        row.addWidget(color_btn)

        pos_spin = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2)
        pos_spin.setValue(stop.position)
        pos_spin.valueChanged.connect(
            lambda v, idx=index: self._on_gradient_pos_changed(idx, v)
        )
        row.addWidget(pos_spin)

        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda _, idx=index: self._on_remove_gradient_stop(idx))
        row.addWidget(remove_btn)

        layout.addLayout(row)
        self._gradient_stop_widgets.append(
            {"color_btn": color_btn, "pos_spin": pos_spin}
        )

    # -- Event handlers --

    def _on_viz_type_changed(self, index: int) -> None:
        if self._preset is None or self._rebuilding:
            return
        old_type = self._preset.visualization.visualization_type
        old_params = dict(self._preset.visualization.params)
        self._viz_memory[old_type] = old_params

        new_type = self._viz_combo.itemData(index)
        restored = dict(self._viz_memory.get(new_type, {}))
        self._preset.visualization = VisualizationParams(
            visualization_type=new_type, params=restored,
        )
        self._build_param_widgets(new_type, restored)
        self._emit_update()

    def _on_reset_all_params(self) -> None:
        """Reset current visualization params to schema defaults."""
        if self._preset is None or self._rebuilding:
            return
        current_type = self._preset.visualization.visualization_type
        self._viz_memory.pop(current_type, None)
        self._preset.visualization = VisualizationParams(
            visualization_type=current_type, params={},
        )
        self._build_param_widgets(current_type, {})
        self._emit_update()

    def _on_param_changed(self, name: str, value: Any) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.visualization.params[name] = value
        self._emit_update()

    def _show_param_context_menu(
        self, param_name: str, widget: QWidget, pos: Any,
    ) -> None:
        """Show right-click context menu with 'Reset to default' for a parameter."""
        if self._preset is None:
            return
        viz_type = self._preset.visualization.visualization_type
        registry = VisualizationRegistry()
        try:
            viz_class = registry.get(viz_type)
        except KeyError:
            return
        schema = viz_class.PARAM_SCHEMA.get(param_name)
        if schema is None or "default" not in schema:
            return

        menu = QMenu(self)
        reset_action = QAction(f"Reset to default ({schema['default']})", self)
        default_val = schema["default"]

        def _do_reset() -> None:
            param_type = schema.get("type", "float")
            if param_type in ("int", "float") and isinstance(widget, DragSpinBox):
                widget.setValue(default_val)
            elif param_type == "bool" and isinstance(widget, QCheckBox):
                widget.setChecked(bool(default_val))
            elif param_type == "choice" and isinstance(widget, NoScrollComboBox):
                idx = widget.findData(default_val)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif param_type == "color" and isinstance(widget, QPushButton):
                widget.setStyleSheet(
                    f"background-color: {default_val}; border: 1px solid #555;"
                )
                self._on_param_changed(param_name, default_val)

        reset_action.triggered.connect(_do_reset)
        menu.addAction(reset_action)
        menu.exec(widget.mapToGlobal(pos))

    @staticmethod
    def _elide_path(path: str, max_len: int = 20) -> str:
        if len(path) <= max_len:
            return path
        import os
        return "..." + os.sep + os.path.basename(path)

    def _on_file_param_browse(
        self, param_name: str, label: QLabel, file_filter: str,
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
        if path:
            label.setText(self._elide_path(path))
            self._on_param_changed(param_name, path)

    def _on_file_param_clear(self, param_name: str, label: QLabel) -> None:
        label.setText("No image")
        self._on_param_changed(param_name, "")

    def _on_color_param_clicked(self, param_name: str, button: QPushButton) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current_hex = self._preset.visualization.params.get(param_name, "#000000")
        current = QColor(current_hex)
        color = QColorDialog.getColor(current, self, "Pick Color")
        if color.isValid():
            hex_color = color.name().upper()
            button.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._on_param_changed(param_name, hex_color)

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
            self._emit_update()

    def _on_add_color(self) -> None:
        if self._preset is None:
            return
        color = QColorDialog.getColor(parent=self, title="Add Color")
        if color.isValid():
            self._preset.color_palette.append(color.name().upper())
            self.set_preset(self._preset)
            self._emit_update()

    def _on_remove_color(self, index: int) -> None:
        if self._preset is None or len(self._preset.color_palette) <= 1:
            return
        self._preset.color_palette.pop(index)
        self.set_preset(self._preset)
        self._emit_update()

    def _on_move_color_up(self, index: int) -> None:
        if self._preset is None or index <= 0:
            return
        self._preset.color_palette[index], self._preset.color_palette[index - 1] = (
            self._preset.color_palette[index - 1],
            self._preset.color_palette[index],
        )
        self.set_preset(self._preset)
        self._emit_update()

    def _on_move_color_down(self, index: int) -> None:
        if self._preset is None or index >= len(self._preset.color_palette) - 1:
            return
        self._preset.color_palette[index], self._preset.color_palette[index + 1] = (
            self._preset.color_palette[index + 1],
            self._preset.color_palette[index],
        )
        self.set_preset(self._preset)
        self._emit_update()

    def _on_bg_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.background.type = self._bg_type_combo.currentData()
        self._rebuild_bg_type_widgets(self._preset.background)
        self._emit_update()

    def _on_bg_image_pick(self) -> None:
        if self._preset is None:
            return
        path = open_background_image(self)
        if path is not None:
            self._preset.background.image_path = str(path)
            self._bg_image_label.setText(str(path))
            self._emit_update()

    def _on_gradient_color_clicked(self, index: int) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        stops = self._preset.background.gradient_stops
        if index >= len(stops):
            return
        current = QColor(stops[index].color)
        color = QColorDialog.getColor(current, self, "Gradient Stop Color")
        if color.isValid():
            hex_color = color.name().upper()
            stops[index].color = hex_color
            self._gradient_stop_widgets[index]["color_btn"].setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._emit_update()

    def _on_gradient_pos_changed(self, index: int, value: float) -> None:
        if self._preset is None or self._rebuilding:
            return
        stops = self._preset.background.gradient_stops
        if index < len(stops):
            stops[index].position = value
            self._emit_update()

    def _on_add_gradient_stop(self) -> None:
        if self._preset is None:
            return
        self._preset.background.gradient_stops.append(
            ColorStop(position=0.5, color="#808080")
        )
        self._rebuild_bg_type_widgets(self._preset.background)
        self._emit_update()

    def _on_remove_gradient_stop(self, index: int) -> None:
        if self._preset is None:
            return
        stops = self._preset.background.gradient_stops
        if len(stops) <= 2:
            return
        stops.pop(index)
        self._rebuild_bg_type_widgets(self._preset.background)
        self._emit_update()

    def _on_bg_color_clicked(self) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.background.color)
        color = QColorDialog.getColor(current, self, "Background Color")
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.background.color = hex_color
            self._bg_color_btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._emit_update()

    def _emit_update(self) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset)

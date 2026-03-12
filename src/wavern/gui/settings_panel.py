"""Dynamic settings panel — auto-generates parameter widgets from PARAM_SCHEMA."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.background_picker import open_background_image
from wavern.presets.schema import BackgroundConfig, ColorStop, Preset, VisualizationParams
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class SettingsPanel(QWidget):
    """Dynamic parameter editor that rebuilds UI from PARAM_SCHEMA."""

    params_changed = Signal(object)  # updated Preset
    background_changed = Signal(object)  # updated BackgroundConfig

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._widgets: dict[str, QWidget] = {}
        self._color_buttons: list[QPushButton] = []
        self._rebuilding: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Scroll area for all settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._content)
        main_layout.addWidget(scroll)

    def set_preset(self, preset: Preset) -> None:
        """Rebuild the settings panel for the given preset."""
        self._preset = preset
        self._widgets.clear()
        self._color_buttons.clear()
        self._rebuilding = True  # Block signals during rebuild

        # Clear existing widgets
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Visualization type selector
        viz_group = QGroupBox("Visualization")
        viz_layout = QFormLayout(viz_group)

        registry = VisualizationRegistry()
        self._viz_combo = QComboBox()
        # Block signals while populating to prevent spurious callbacks
        self._viz_combo.blockSignals(True)
        for info in registry.list_all():
            self._viz_combo.addItem(info["display_name"], info["name"])

        # Set current
        current_type = preset.visualization.visualization_type
        for i in range(self._viz_combo.count()):
            if self._viz_combo.itemData(i) == current_type:
                self._viz_combo.setCurrentIndex(i)
                break
        self._viz_combo.blockSignals(False)

        self._viz_combo.currentIndexChanged.connect(self._on_viz_type_changed)
        viz_layout.addRow("Type:", self._viz_combo)
        self._content_layout.addWidget(viz_group)

        # Visualization parameters
        self._params_group = QGroupBox("Parameters")
        self._params_layout = QFormLayout(self._params_group)
        self._build_param_widgets(current_type, preset.visualization.params)
        self._content_layout.addWidget(self._params_group)

        # Colors
        self._build_color_section(preset)

        # Background
        self._build_background_section(preset)

        # Analysis settings
        self._build_analysis_section(preset)

        self._rebuilding = False

    def _build_param_widgets(self, viz_type: str, current_params: dict[str, Any]) -> None:
        """Build parameter widgets from the visualization's PARAM_SCHEMA."""
        # Clear existing
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
                widget = QSpinBox()
                widget.setRange(schema.get("min", 0), schema.get("max", 9999))
                widget.setValue(int(current_val or 0))
                widget.valueChanged.connect(lambda v, n=param_name: self._on_param_changed(n, v))

            elif param_type == "float":
                widget = QDoubleSpinBox()
                widget.setRange(schema.get("min", 0.0), schema.get("max", 100.0))
                widget.setSingleStep(0.01)
                widget.setDecimals(3)
                widget.setValue(float(current_val or 0.0))
                widget.valueChanged.connect(lambda v, n=param_name: self._on_param_changed(n, v))

            elif param_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(current_val))
                widget.stateChanged.connect(
                    lambda v, n=param_name: self._on_param_changed(n, bool(v))
                )

            elif param_type == "choice":
                widget = QComboBox()
                for choice in schema.get("choices", []):
                    widget.addItem(str(choice), choice)
                if current_val is not None:
                    idx = widget.findData(current_val)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                widget.currentIndexChanged.connect(
                    lambda _, n=param_name, w=widget: self._on_param_changed(n, w.currentData())
                )

            else:
                continue

            self._widgets[param_name] = widget
            self._params_layout.addRow(f"{label}:", widget)

    def _build_color_section(self, preset: Preset) -> None:
        """Build color palette editor."""
        color_group = QGroupBox("Colors")
        color_layout = QVBoxLayout(color_group)

        for i, color_hex in enumerate(preset.color_palette):
            row = QHBoxLayout()

            # Move up button
            up_btn = QPushButton("▲")
            up_btn.setFixedSize(24, 24)
            up_btn.setEnabled(i > 0)
            up_btn.clicked.connect(lambda _, idx=i: self._on_move_color_up(idx))
            row.addWidget(up_btn)

            # Move down button
            down_btn = QPushButton("▼")
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
            remove_btn.setFixedSize(24, 24)
            remove_btn.clicked.connect(lambda _, idx=i: self._on_remove_color(idx))
            row.addWidget(remove_btn)

            color_layout.addLayout(row)
            self._color_buttons.append(btn)

        add_btn = QPushButton("+ Add Color")
        add_btn.clicked.connect(self._on_add_color)
        color_layout.addWidget(add_btn)

        self._content_layout.addWidget(color_group)

    def _build_background_section(self, preset: Preset) -> None:
        """Build background settings with type-specific widgets."""
        self._bg_group = QGroupBox("Background")
        self._bg_layout = QFormLayout(self._bg_group)

        self._bg_type_combo = QComboBox()
        self._bg_type_combo.blockSignals(True)
        for bg_type in ["solid", "none", "image", "gradient"]:
            self._bg_type_combo.addItem(bg_type, bg_type)
        idx = self._bg_type_combo.findData(preset.background.type)
        if idx >= 0:
            self._bg_type_combo.setCurrentIndex(idx)
        self._bg_type_combo.blockSignals(False)
        self._bg_type_combo.currentIndexChanged.connect(self._on_bg_changed)
        self._bg_layout.addRow("Type:", self._bg_type_combo)

        # Container for type-specific widgets (rebuilt on type change)
        self._bg_type_container = QWidget()
        self._bg_type_container_layout = QVBoxLayout(self._bg_type_container)
        self._bg_type_container_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.addRow(self._bg_type_container)

        self._rebuild_bg_type_widgets(preset.background)
        self._content_layout.addWidget(self._bg_group)

    def _rebuild_bg_type_widgets(self, bg: BackgroundConfig) -> None:
        """Rebuild the type-specific background widgets inside the container."""
        layout = self._bg_type_container_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear sub-layout items
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
        """Add a single gradient stop editor row."""
        row = QHBoxLayout()

        color_btn = QPushButton()
        color_btn.setFixedSize(30, 30)
        color_btn.setStyleSheet(
            f"background-color: {stop.color}; border: 1px solid #555;"
        )
        color_btn.clicked.connect(lambda _, idx=index: self._on_gradient_color_clicked(idx))
        row.addWidget(color_btn)

        pos_spin = QDoubleSpinBox()
        pos_spin.setRange(0.0, 1.0)
        pos_spin.setSingleStep(0.05)
        pos_spin.setDecimals(2)
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

    def _build_analysis_section(self, preset: Preset) -> None:
        """Build audio analysis settings."""
        analysis_group = QGroupBox("Analysis")
        analysis_layout = QFormLayout(analysis_group)

        self._fft_size_spin = QSpinBox()
        self._fft_size_spin.setRange(256, 16384)
        self._fft_size_spin.setSingleStep(256)
        self._fft_size_spin.setValue(preset.fft_size)
        self._fft_size_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("FFT Size:", self._fft_size_spin)

        self._smoothing_spin = QDoubleSpinBox()
        self._smoothing_spin.setRange(0.0, 0.99)
        self._smoothing_spin.setSingleStep(0.05)
        self._smoothing_spin.setValue(preset.smoothing)
        self._smoothing_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("Smoothing:", self._smoothing_spin)

        self._beat_sens_spin = QDoubleSpinBox()
        self._beat_sens_spin.setRange(0.1, 5.0)
        self._beat_sens_spin.setSingleStep(0.1)
        self._beat_sens_spin.setValue(preset.beat_sensitivity)
        self._beat_sens_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("Beat Sensitivity:", self._beat_sens_spin)

        self._content_layout.addWidget(analysis_group)

    def _on_viz_type_changed(self, index: int) -> None:
        if self._preset is None or self._rebuilding:
            return
        new_type = self._viz_combo.itemData(index)
        self._preset.visualization = VisualizationParams(visualization_type=new_type, params={})
        self._build_param_widgets(new_type, {})
        self._emit_update()

    def _on_param_changed(self, name: str, value: Any) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.visualization.params[name] = value
        self._emit_update()

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
            self.set_preset(self._preset)  # Rebuild
            self._emit_update()

    def _on_remove_color(self, index: int) -> None:
        if self._preset is None or len(self._preset.color_palette) <= 1:
            return
        self._preset.color_palette.pop(index)
        self.set_preset(self._preset)  # Rebuild
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
            return  # need at least 2 stops
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

    def _on_move_color_up(self, index: int) -> None:
        if self._preset is None or index <= 0:
            return
        # Swap with previous color
        self._preset.color_palette[index], self._preset.color_palette[index - 1] = (
            self._preset.color_palette[index - 1],
            self._preset.color_palette[index],
        )
        self.set_preset(self._preset)
        self._emit_update()

    def _on_move_color_down(self, index: int) -> None:
        if self._preset is None or index >= len(self._preset.color_palette) - 1:
            return
        # Swap with next color
        self._preset.color_palette[index], self._preset.color_palette[index + 1] = (
            self._preset.color_palette[index + 1],
            self._preset.color_palette[index],
        )
        self.set_preset(self._preset)
        self._emit_update()

    def _on_analysis_changed(self) -> None:
        if self._preset is None:
            return
        self._preset.fft_size = self._fft_size_spin.value()
        self._preset.smoothing = self._smoothing_spin.value()
        self._preset.beat_sensitivity = self._beat_sens_spin.value()
        self._emit_update()

    def _emit_update(self) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset)

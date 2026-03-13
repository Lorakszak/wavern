"""Dynamic settings panel — auto-generates parameter widgets from PARAM_SCHEMA."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.background_picker import open_background_image
from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.help_button import make_help_button
from wavern.core.text_overlay import AVAILABLE_FONTS, COUNTDOWN_FORMATS
from wavern.presets.schema import BackgroundConfig, ColorStop, OverlayConfig, Preset, VisualizationParams
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
        self._section_states: dict[str, bool] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        self._content_layout = QVBoxLayout(self)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def set_preset(self, preset: Preset) -> None:
        """Rebuild the settings panel for the given preset."""
        self._preset = preset
        self._widgets.clear()
        self._color_buttons.clear()
        self._rebuilding = True

        # Save section expanded states before clearing
        self._save_section_states()

        # Clear existing widgets
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # --- Visualization (type + parameters merged) ---
        self._viz_section = CollapsibleSection("Visualization")
        viz_content = QWidget()
        viz_layout = QVBoxLayout(viz_content)
        viz_layout.setContentsMargins(4, 0, 4, 0)

        # Type selector
        type_form = QFormLayout()
        registry = VisualizationRegistry()
        self._viz_combo = QComboBox()
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
        type_form.addRow("Type:", self._viz_combo)
        viz_layout.addLayout(type_form)

        # Parameters
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

        # --- Overlay ---
        self._overlay_section = CollapsibleSection("Overlay")
        self._build_overlay_section(preset)
        self._content_layout.addWidget(self._overlay_section)

        # --- Analysis ---
        self._analysis_section = CollapsibleSection("Analysis")
        self._build_analysis_section(preset)
        self._content_layout.addWidget(self._analysis_section)

        # Restore section states
        self._restore_section_states()

        self._rebuilding = False

    def _save_section_states(self) -> None:
        """Save expanded/collapsed state of all sections."""
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
            "Overlay": "_overlay_section",
            "Analysis": "_analysis_section",
        }
        for section_name, attr in attr_map.items():
            if hasattr(self, attr):
                self._section_states[section_name] = getattr(self, attr).is_expanded()

    def _restore_section_states(self) -> None:
        """Restore expanded/collapsed state of all sections."""
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
            "Overlay": "_overlay_section",
            "Analysis": "_analysis_section",
        }
        for section_name, expanded in self._section_states.items():
            attr = attr_map.get(section_name)
            if attr and hasattr(self, attr):
                getattr(self, attr).set_expanded(expanded)

    def _build_param_widgets(self, viz_type: str, current_params: dict[str, Any]) -> None:
        """Build parameter widgets from the visualization's PARAM_SCHEMA."""
        # Clear existing (handles both direct widgets and nested layouts from help buttons)
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

            range_label: QLabel | None = None

            if param_type == "int":
                widget = QSpinBox()
                p_min = schema.get("min", 0)
                p_max = schema.get("max", 9999)
                widget.setRange(p_min, p_max)
                widget.setValue(int(current_val or 0))
                widget.valueChanged.connect(lambda v, n=param_name: self._on_param_changed(n, v))
                range_label = self._make_range_label(f"<{p_min}, {p_max}>")

            elif param_type == "float":
                widget = QDoubleSpinBox()
                p_min = schema.get("min", 0.0)
                p_max = schema.get("max", 100.0)
                widget.setRange(p_min, p_max)
                widget.setSingleStep(0.01)
                widget.setDecimals(3)
                widget.setValue(float(current_val or 0.0))
                widget.valueChanged.connect(lambda v, n=param_name: self._on_param_changed(n, v))
                range_label = self._make_range_label(f"<{p_min:g}, {p_max:g}>")

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
            description = schema.get("description")
            if range_label or description:
                row = QHBoxLayout()
                row.addWidget(widget, stretch=1)
                if range_label:
                    row.addWidget(range_label)
                if description:
                    row.addWidget(make_help_button(description))
                self._params_layout.addRow(f"{label}:", row)
            else:
                self._params_layout.addRow(f"{label}:", widget)

    @staticmethod
    def _make_range_label(text: str) -> QLabel:
        """Create a small muted label showing a parameter's min–max range."""
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666; font-size: 10px;")
        return lbl

    def _build_color_section(self, preset: Preset) -> None:
        """Build color palette editor."""
        color_content = QWidget()
        color_layout = QVBoxLayout(color_content)
        color_layout.setContentsMargins(4, 0, 4, 0)

        for i, color_hex in enumerate(preset.color_palette):
            row = QHBoxLayout()

            up_btn = QPushButton("\u25B2")
            up_btn.setFixedSize(24, 24)
            up_btn.setEnabled(i > 0)
            up_btn.clicked.connect(lambda _, idx=i: self._on_move_color_up(idx))
            row.addWidget(up_btn)

            down_btn = QPushButton("\u25BC")
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

        self._color_section.set_content(color_content)

    def _build_background_section(self, preset: Preset) -> None:
        """Build background settings with type-specific widgets."""
        bg_content = QWidget()
        self._bg_layout = QFormLayout(bg_content)
        self._bg_layout.setContentsMargins(4, 0, 4, 0)

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
        self._bg_section.set_content(bg_content)

    def _rebuild_bg_type_widgets(self, bg: BackgroundConfig) -> None:
        """Rebuild the type-specific background widgets inside the container."""
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
        analysis_content = QWidget()
        analysis_layout = QFormLayout(analysis_content)
        analysis_layout.setContentsMargins(4, 0, 4, 0)

        self._fft_size_spin = QSpinBox()
        self._fft_size_spin.setRange(256, 16384)
        self._fft_size_spin.setSingleStep(256)
        self._fft_size_spin.setValue(preset.fft_size)
        self._fft_size_spin.valueChanged.connect(self._on_analysis_changed)
        fft_row = QHBoxLayout()
        fft_row.addWidget(self._fft_size_spin, stretch=1)
        fft_row.addWidget(self._make_range_label("<256, 16384>"))
        fft_row.addWidget(make_help_button(
            "Number of frequency bins. Higher = finer frequency detail but slower response. "
            "Must be power of 2. 2048=balanced, 4096=detailed, 8192=very detailed."
        ))
        analysis_layout.addRow("FFT Size:", fft_row)

        self._smoothing_spin = QDoubleSpinBox()
        self._smoothing_spin.setRange(0.0, 0.99)
        self._smoothing_spin.setSingleStep(0.05)
        self._smoothing_spin.setValue(preset.smoothing)
        self._smoothing_spin.valueChanged.connect(self._on_analysis_changed)
        smoothing_row = QHBoxLayout()
        smoothing_row.addWidget(self._smoothing_spin, stretch=1)
        smoothing_row.addWidget(self._make_range_label("<0, 0.99>"))
        smoothing_row.addWidget(make_help_button(
            "Temporal smoothing (0\u20130.99). Higher values make visuals react more slowly. "
            "0=raw, 0.3=moderate, 0.8=very smooth."
        ))
        analysis_layout.addRow("Smoothing:", smoothing_row)

        self._beat_sens_spin = QDoubleSpinBox()
        self._beat_sens_spin.setRange(0.1, 5.0)
        self._beat_sens_spin.setSingleStep(0.1)
        self._beat_sens_spin.setValue(preset.beat_sensitivity)
        self._beat_sens_spin.valueChanged.connect(self._on_analysis_changed)
        beat_row = QHBoxLayout()
        beat_row.addWidget(self._beat_sens_spin, stretch=1)
        beat_row.addWidget(self._make_range_label("<0.1, 5.0>"))
        beat_row.addWidget(make_help_button(
            "How easily beats are detected. Lower=only strong beats, "
            "higher=triggers on quiet transients. 1.0=default."
        ))
        analysis_layout.addRow("Beat Sensitivity:", beat_row)

        self._analysis_section.set_content(analysis_content)

    def _build_overlay_section(self, preset: Preset) -> None:
        """Build text overlay controls (title, countdown, position, font)."""
        content = QWidget()
        layout = QFormLayout(content)
        layout.setContentsMargins(4, 0, 4, 0)

        cfg = preset.overlay

        # --- Title ---
        self._overlay_title_cb = QCheckBox()
        self._overlay_title_cb.setChecked(cfg.title_enabled)
        self._overlay_title_cb.stateChanged.connect(self._on_overlay_changed)
        layout.addRow("Show Title:", self._overlay_title_cb)

        self._overlay_title_edit = QLineEdit()
        self._overlay_title_edit.setText(cfg.title_text)
        self._overlay_title_edit.setPlaceholderText("Song title...")
        self._overlay_title_edit.setMaxLength(200)
        self._overlay_title_edit.textChanged.connect(self._on_overlay_changed)
        layout.addRow("Title Text:", self._overlay_title_edit)

        # --- Countdown ---
        self._overlay_countdown_cb = QCheckBox()
        self._overlay_countdown_cb.setChecked(cfg.countdown_enabled)
        self._overlay_countdown_cb.stateChanged.connect(self._on_overlay_changed)
        layout.addRow("Show Countdown:", self._overlay_countdown_cb)

        self._overlay_format_combo = QComboBox()
        self._overlay_format_combo.blockSignals(True)
        for key, label in COUNTDOWN_FORMATS.items():
            self._overlay_format_combo.addItem(label, key)
        idx = self._overlay_format_combo.findData(cfg.countdown_format)
        if idx >= 0:
            self._overlay_format_combo.setCurrentIndex(idx)
        self._overlay_format_combo.blockSignals(False)
        self._overlay_format_combo.currentIndexChanged.connect(self._on_overlay_changed)
        layout.addRow("Format:", self._overlay_format_combo)

        # --- Position ---
        self._overlay_link_cb = QCheckBox("Link positions")
        self._overlay_link_cb.setChecked(cfg.link_positions)
        self._overlay_link_cb.stateChanged.connect(self._on_overlay_link_changed)
        layout.addRow(self._overlay_link_cb)

        self._overlay_title_x = QDoubleSpinBox()
        self._overlay_title_x.setRange(0.0, 1.0)
        self._overlay_title_x.setSingleStep(0.05)
        self._overlay_title_x.setDecimals(2)
        self._overlay_title_x.setValue(cfg.title_x)
        self._overlay_title_x.valueChanged.connect(self._on_overlay_pos_changed)

        self._overlay_title_y = QDoubleSpinBox()
        self._overlay_title_y.setRange(0.0, 1.0)
        self._overlay_title_y.setSingleStep(0.05)
        self._overlay_title_y.setDecimals(2)
        self._overlay_title_y.setValue(cfg.title_y)
        self._overlay_title_y.valueChanged.connect(self._on_overlay_pos_changed)

        pos_label = "Position:" if cfg.link_positions else "Title Pos:"
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("X"))
        pos_row.addWidget(self._overlay_title_x)
        pos_row.addWidget(QLabel("Y"))
        pos_row.addWidget(self._overlay_title_y)
        self._overlay_pos_label = QLabel(pos_label)
        layout.addRow(self._overlay_pos_label, pos_row)

        self._overlay_cd_row_widget = QWidget()
        cd_row = QHBoxLayout(self._overlay_cd_row_widget)
        cd_row.setContentsMargins(0, 0, 0, 0)

        self._overlay_countdown_x = QDoubleSpinBox()
        self._overlay_countdown_x.setRange(0.0, 1.0)
        self._overlay_countdown_x.setSingleStep(0.05)
        self._overlay_countdown_x.setDecimals(2)
        self._overlay_countdown_x.setValue(cfg.countdown_x)
        self._overlay_countdown_x.valueChanged.connect(self._on_overlay_changed)

        self._overlay_countdown_y = QDoubleSpinBox()
        self._overlay_countdown_y.setRange(0.0, 1.0)
        self._overlay_countdown_y.setSingleStep(0.05)
        self._overlay_countdown_y.setDecimals(2)
        self._overlay_countdown_y.setValue(cfg.countdown_y)
        self._overlay_countdown_y.valueChanged.connect(self._on_overlay_changed)

        cd_row.addWidget(QLabel("X"))
        cd_row.addWidget(self._overlay_countdown_x)
        cd_row.addWidget(QLabel("Y"))
        cd_row.addWidget(self._overlay_countdown_y)

        self._overlay_cd_pos_label = QLabel("Countdown Pos:")
        layout.addRow(self._overlay_cd_pos_label, self._overlay_cd_row_widget)

        # Hide countdown position row when linked
        self._overlay_cd_pos_label.setVisible(not cfg.link_positions)
        self._overlay_cd_row_widget.setVisible(not cfg.link_positions)

        # --- Font ---
        self._overlay_font_combo = QComboBox()
        self._overlay_font_combo.blockSignals(True)
        for key, display_name in AVAILABLE_FONTS():
            self._overlay_font_combo.addItem(display_name, key)
        idx = self._overlay_font_combo.findData(cfg.font_family)
        if idx >= 0:
            self._overlay_font_combo.setCurrentIndex(idx)
        self._overlay_font_combo.blockSignals(False)
        self._overlay_font_combo.currentIndexChanged.connect(self._on_overlay_changed)
        layout.addRow("Font:", self._overlay_font_combo)

        self._overlay_bold_cb = QCheckBox()
        self._overlay_bold_cb.setChecked(cfg.font_bold)
        self._overlay_bold_cb.stateChanged.connect(self._on_overlay_changed)
        layout.addRow("Bold:", self._overlay_bold_cb)

        self._overlay_font_size = QSpinBox()
        self._overlay_font_size.setRange(8, 120)
        self._overlay_font_size.setValue(cfg.font_size)
        self._overlay_font_size.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Font Size:", self._overlay_font_size)

        self._overlay_font_color_btn = QPushButton()
        self._overlay_font_color_btn.setFixedSize(30, 30)
        self._overlay_font_color_btn.setStyleSheet(
            f"background-color: {cfg.font_color}; border: 1px solid #555;"
        )
        self._overlay_font_color_btn.clicked.connect(self._on_overlay_font_color_clicked)
        layout.addRow("Font Color:", self._overlay_font_color_btn)

        self._overlay_opacity = QDoubleSpinBox()
        self._overlay_opacity.setRange(0.0, 1.0)
        self._overlay_opacity.setSingleStep(0.05)
        self._overlay_opacity.setDecimals(2)
        self._overlay_opacity.setValue(cfg.font_opacity)
        self._overlay_opacity.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Opacity:", self._overlay_opacity)

        # --- Outline ---
        self._overlay_outline_cb = QCheckBox()
        self._overlay_outline_cb.setChecked(cfg.outline_enabled)
        self._overlay_outline_cb.stateChanged.connect(self._on_overlay_changed)
        layout.addRow("Outline:", self._overlay_outline_cb)

        self._overlay_outline_color_btn = QPushButton()
        self._overlay_outline_color_btn.setFixedSize(30, 30)
        self._overlay_outline_color_btn.setStyleSheet(
            f"background-color: {cfg.outline_color}; border: 1px solid #555;"
        )
        self._overlay_outline_color_btn.clicked.connect(
            self._on_overlay_outline_color_clicked
        )
        layout.addRow("Outline Color:", self._overlay_outline_color_btn)

        self._overlay_outline_width = QSpinBox()
        self._overlay_outline_width.setRange(1, 10)
        self._overlay_outline_width.setValue(cfg.outline_width)
        self._overlay_outline_width.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Outline Width:", self._overlay_outline_width)

        # --- Shadow ---
        self._overlay_shadow_cb = QCheckBox()
        self._overlay_shadow_cb.setChecked(cfg.shadow_enabled)
        self._overlay_shadow_cb.stateChanged.connect(self._on_overlay_changed)
        layout.addRow("Shadow:", self._overlay_shadow_cb)

        self._overlay_shadow_color_btn = QPushButton()
        self._overlay_shadow_color_btn.setFixedSize(30, 30)
        self._overlay_shadow_color_btn.setStyleSheet(
            f"background-color: {cfg.shadow_color}; border: 1px solid #555;"
        )
        self._overlay_shadow_color_btn.clicked.connect(
            self._on_overlay_shadow_color_clicked
        )
        layout.addRow("Shadow Color:", self._overlay_shadow_color_btn)

        self._overlay_shadow_opacity = QDoubleSpinBox()
        self._overlay_shadow_opacity.setRange(0.0, 1.0)
        self._overlay_shadow_opacity.setSingleStep(0.05)
        self._overlay_shadow_opacity.setDecimals(2)
        self._overlay_shadow_opacity.setValue(cfg.shadow_opacity)
        self._overlay_shadow_opacity.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Shadow Opacity:", self._overlay_shadow_opacity)

        shadow_offset_row = QHBoxLayout()
        self._overlay_shadow_ox = QSpinBox()
        self._overlay_shadow_ox.setRange(-20, 20)
        self._overlay_shadow_ox.setValue(cfg.shadow_offset_x)
        self._overlay_shadow_ox.valueChanged.connect(self._on_overlay_changed)
        self._overlay_shadow_oy = QSpinBox()
        self._overlay_shadow_oy.setRange(-20, 20)
        self._overlay_shadow_oy.setValue(cfg.shadow_offset_y)
        self._overlay_shadow_oy.valueChanged.connect(self._on_overlay_changed)
        shadow_offset_row.addWidget(QLabel("X"))
        shadow_offset_row.addWidget(self._overlay_shadow_ox)
        shadow_offset_row.addWidget(QLabel("Y"))
        shadow_offset_row.addWidget(self._overlay_shadow_oy)
        layout.addRow("Shadow Offset:", shadow_offset_row)

        self._overlay_section.set_content(content)

    def _on_overlay_changed(self) -> None:
        """Collect all overlay widget values into preset.overlay and emit update."""
        if self._preset is None or self._rebuilding:
            return
        cfg = self._preset.overlay
        cfg.title_enabled = self._overlay_title_cb.isChecked()
        cfg.title_text = self._overlay_title_edit.text()
        cfg.countdown_enabled = self._overlay_countdown_cb.isChecked()
        cfg.countdown_format = self._overlay_format_combo.currentData()
        cfg.link_positions = self._overlay_link_cb.isChecked()
        cfg.title_x = self._overlay_title_x.value()
        cfg.title_y = self._overlay_title_y.value()
        cfg.countdown_x = self._overlay_countdown_x.value()
        cfg.countdown_y = self._overlay_countdown_y.value()
        cfg.font_family = self._overlay_font_combo.currentData()
        cfg.font_bold = self._overlay_bold_cb.isChecked()
        cfg.font_size = self._overlay_font_size.value()
        cfg.font_opacity = self._overlay_opacity.value()
        cfg.outline_enabled = self._overlay_outline_cb.isChecked()
        cfg.outline_width = self._overlay_outline_width.value()
        cfg.shadow_enabled = self._overlay_shadow_cb.isChecked()
        cfg.shadow_opacity = self._overlay_shadow_opacity.value()
        cfg.shadow_offset_x = self._overlay_shadow_ox.value()
        cfg.shadow_offset_y = self._overlay_shadow_oy.value()
        self._emit_update()

    def _on_overlay_pos_changed(self) -> None:
        """Handle title position change — sync countdown pos when linked."""
        if self._preset is None or self._rebuilding:
            return
        if self._overlay_link_cb.isChecked():
            self._overlay_countdown_x.blockSignals(True)
            self._overlay_countdown_y.blockSignals(True)
            self._overlay_countdown_x.setValue(self._overlay_title_x.value())
            self._overlay_countdown_y.setValue(self._overlay_title_y.value())
            self._overlay_countdown_x.blockSignals(False)
            self._overlay_countdown_y.blockSignals(False)
        self._on_overlay_changed()

    def _on_overlay_link_changed(self, state: int) -> None:
        """Toggle linked/independent positions for title and countdown."""
        linked = bool(state)
        self._overlay_pos_label.setText("Position:" if linked else "Title Pos:")
        # Hide/show countdown position row
        self._overlay_cd_pos_label.setVisible(not linked)
        self._overlay_cd_row_widget.setVisible(not linked)

        if linked:
            self._overlay_countdown_x.blockSignals(True)
            self._overlay_countdown_y.blockSignals(True)
            self._overlay_countdown_x.setValue(self._overlay_title_x.value())
            self._overlay_countdown_y.setValue(self._overlay_title_y.value())
            self._overlay_countdown_x.blockSignals(False)
            self._overlay_countdown_y.blockSignals(False)
        self._on_overlay_changed()

    def _on_overlay_font_color_clicked(self) -> None:
        """Open color picker for overlay font color."""
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.overlay.font_color)
        color = QColorDialog.getColor(current, self, "Font Color")
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.overlay.font_color = hex_color
            self._overlay_font_color_btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._emit_update()

    def _on_overlay_outline_color_clicked(self) -> None:
        """Open color picker for outline color."""
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.overlay.outline_color)
        color = QColorDialog.getColor(current, self, "Outline Color")
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.overlay.outline_color = hex_color
            self._overlay_outline_color_btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._emit_update()

    def _on_overlay_shadow_color_clicked(self) -> None:
        """Open color picker for shadow color."""
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.overlay.shadow_color)
        color = QColorDialog.getColor(current, self, "Shadow Color")
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.overlay.shadow_color = hex_color
            self._overlay_shadow_color_btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;"
            )
            self._emit_update()

    def set_viz_by_index(self, index: int) -> None:
        """Switch visualization type by combo index (0-based). No-op if out of range."""
        if self._preset is None or index >= self._viz_combo.count():
            return
        self._viz_combo.setCurrentIndex(index)

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

    @staticmethod
    def _elide_path(path: str, max_len: int = 20) -> str:
        """Shorten a file path for display."""
        if len(path) <= max_len:
            return path
        import os
        return "..." + os.sep + os.path.basename(path)

    def _on_file_param_browse(
        self, param_name: str, label: QLabel, file_filter: str,
    ) -> None:
        """Open a file dialog for a file-type parameter."""
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", file_filter)
        if path:
            label.setText(self._elide_path(path))
            self._on_param_changed(param_name, path)

    def _on_file_param_clear(self, param_name: str, label: QLabel) -> None:
        """Clear a file-type parameter."""
        label.setText("No image")
        self._on_param_changed(param_name, "")

    def _on_color_param_clicked(self, param_name: str, button: QPushButton) -> None:
        """Handle click on a color-type parameter swatch."""
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

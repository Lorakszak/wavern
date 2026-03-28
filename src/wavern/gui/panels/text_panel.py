"""Text overlay panel — title, countdown, position, font, outline, shadow."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.change_scope import ChangeScope
from wavern.gui.no_scroll_combo import NoScrollComboBox

from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.core.text_overlay import AVAILABLE_FONTS, COUNTDOWN_FORMATS
from wavern.presets.schema import OverlayConfig, Preset

logger = logging.getLogger(__name__)


class TextPanel(QWidget):
    """Text overlay settings: title, countdown, position, font, outline, shadow."""

    params_changed = Signal(object, object)  # (Preset, ChangeScope)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = layout

        self._overlay_section = CollapsibleSection("Overlay")
        self._build_overlay_section()
        self._content_layout.addWidget(self._overlay_section)

    def set_preset(self, preset: Preset) -> None:
        """Update the text overlay panel for the given preset."""
        self.update_values(preset)

    def update_values(self, preset: Preset) -> None:
        """Update widget values in-place without rebuilding."""
        self._preset = preset
        self._rebuilding = True
        cfg = preset.overlay

        # Block signals on all value-bearing widgets
        signal_widgets = [
            self._overlay_title_cb, self._overlay_title_edit,
            self._overlay_countdown_cb, self._overlay_format_combo,
            self._overlay_link_cb,
            self._overlay_title_x, self._overlay_title_y,
            self._overlay_countdown_x, self._overlay_countdown_y,
            self._overlay_font_combo, self._overlay_bold_cb,
            self._overlay_font_size, self._overlay_opacity,
            self._overlay_outline_cb, self._overlay_outline_width,
            self._overlay_shadow_cb, self._overlay_shadow_opacity,
            self._overlay_shadow_ox, self._overlay_shadow_oy,
        ]
        for w in signal_widgets:
            w.blockSignals(True)

        # Update values
        self._overlay_title_cb.setChecked(cfg.title_enabled)
        self._overlay_title_edit.setText(cfg.title_text)
        self._overlay_countdown_cb.setChecked(cfg.countdown_enabled)
        idx = self._overlay_format_combo.findData(cfg.countdown_format)
        if idx >= 0:
            self._overlay_format_combo.setCurrentIndex(idx)
        self._overlay_link_cb.setChecked(cfg.link_positions)
        self._overlay_title_x.setValue(cfg.title_x)
        self._overlay_title_y.setValue(cfg.title_y)
        self._overlay_countdown_x.setValue(cfg.countdown_x)
        self._overlay_countdown_y.setValue(cfg.countdown_y)
        idx = self._overlay_font_combo.findData(cfg.font_family)
        if idx >= 0:
            self._overlay_font_combo.setCurrentIndex(idx)
        self._overlay_bold_cb.setChecked(cfg.font_bold)
        self._overlay_font_size.setValue(cfg.font_size)
        self._overlay_opacity.setValue(cfg.font_opacity)
        self._overlay_outline_cb.setChecked(cfg.outline_enabled)
        self._overlay_outline_width.setValue(cfg.outline_width)
        self._overlay_shadow_cb.setChecked(cfg.shadow_enabled)
        self._overlay_shadow_opacity.setValue(cfg.shadow_opacity)
        self._overlay_shadow_ox.setValue(cfg.shadow_offset_x)
        self._overlay_shadow_oy.setValue(cfg.shadow_offset_y)

        # Update color button stylesheets (no signals emitted)
        self._overlay_font_color_btn.setStyleSheet(
            f"background-color: {cfg.font_color}; border: 1px solid #555;"
        )
        self._overlay_outline_color_btn.setStyleSheet(
            f"background-color: {cfg.outline_color}; border: 1px solid #555;"
        )
        self._overlay_shadow_color_btn.setStyleSheet(
            f"background-color: {cfg.shadow_color}; border: 1px solid #555;"
        )

        # Update visibility based on link_positions
        self._overlay_pos_label.setText("Position:" if cfg.link_positions else "Title Pos:")
        self._overlay_cd_pos_label.setVisible(not cfg.link_positions)
        self._overlay_cd_row_widget.setVisible(not cfg.link_positions)

        for w in signal_widgets:
            w.blockSignals(False)
        self._rebuilding = False

    def _build_overlay_section(self) -> None:
        """Build text overlay controls (title, countdown, position, font)."""
        content = QWidget()
        layout = QFormLayout(content)
        layout.setContentsMargins(4, 0, 4, 0)

        cfg = OverlayConfig()

        # --- Reset All ---
        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedWidth(90)
        reset_btn.clicked.connect(self._on_reset_all_overlay)
        layout.addRow("", reset_btn)

        # --- Title ---
        self._overlay_title_cb = QCheckBox()
        self._overlay_title_cb.setChecked(cfg.title_enabled)
        self._overlay_title_cb.toggled.connect(self._on_overlay_changed)
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
        self._overlay_countdown_cb.toggled.connect(self._on_overlay_changed)
        layout.addRow("Show Countdown:", self._overlay_countdown_cb)

        self._overlay_format_combo = NoScrollComboBox()
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
        self._overlay_link_cb.toggled.connect(self._on_overlay_link_changed)
        layout.addRow(self._overlay_link_cb)

        self._overlay_title_x = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=0.5)
        self._overlay_title_x.setValue(cfg.title_x)
        self._overlay_title_x.valueChanged.connect(self._on_overlay_pos_changed)

        self._overlay_title_y = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=0.05)
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

        self._overlay_countdown_x = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=0.5)
        self._overlay_countdown_x.setValue(cfg.countdown_x)
        self._overlay_countdown_x.valueChanged.connect(self._on_overlay_changed)

        self._overlay_countdown_y = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=0.05)
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
        self._overlay_font_combo = NoScrollComboBox()
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
        self._overlay_bold_cb.toggled.connect(self._on_overlay_changed)
        layout.addRow("Bold:", self._overlay_bold_cb)

        self._overlay_font_size = DragSpinBox(minimum=8, maximum=120, step=1, decimals=0, default_value=28)
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

        self._overlay_opacity = DragSpinBox(minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=1.0)
        self._overlay_opacity.setValue(cfg.font_opacity)
        self._overlay_opacity.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Opacity:", self._overlay_opacity)

        # --- Outline ---
        self._overlay_outline_cb = QCheckBox()
        self._overlay_outline_cb.setChecked(cfg.outline_enabled)
        self._overlay_outline_cb.toggled.connect(self._on_overlay_changed)
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

        self._overlay_outline_width = DragSpinBox(minimum=1, maximum=10, step=1, decimals=0, default_value=2)
        self._overlay_outline_width.setValue(cfg.outline_width)
        self._overlay_outline_width.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Outline Width:", self._overlay_outline_width)

        # --- Shadow ---
        self._overlay_shadow_cb = QCheckBox()
        self._overlay_shadow_cb.setChecked(cfg.shadow_enabled)
        self._overlay_shadow_cb.toggled.connect(self._on_overlay_changed)
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

        self._overlay_shadow_opacity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2, default_value=0.7,
        )
        self._overlay_shadow_opacity.setValue(cfg.shadow_opacity)
        self._overlay_shadow_opacity.valueChanged.connect(self._on_overlay_changed)
        layout.addRow("Shadow Opacity:", self._overlay_shadow_opacity)

        shadow_offset_row = QHBoxLayout()
        self._overlay_shadow_ox = DragSpinBox(minimum=-20, maximum=20, step=1, decimals=0, default_value=3)
        self._overlay_shadow_ox.setValue(cfg.shadow_offset_x)
        self._overlay_shadow_ox.valueChanged.connect(self._on_overlay_changed)
        self._overlay_shadow_oy = DragSpinBox(minimum=-20, maximum=20, step=1, decimals=0, default_value=3)
        self._overlay_shadow_oy.setValue(cfg.shadow_offset_y)
        self._overlay_shadow_oy.valueChanged.connect(self._on_overlay_changed)
        shadow_offset_row.addWidget(QLabel("X"))
        shadow_offset_row.addWidget(self._overlay_shadow_ox)
        shadow_offset_row.addWidget(QLabel("Y"))
        shadow_offset_row.addWidget(self._overlay_shadow_oy)
        layout.addRow("Shadow Offset:", shadow_offset_row)

        self._overlay_section.set_content(content)

    def _on_reset_all_overlay(self) -> None:
        """Reset all overlay settings to defaults."""
        if self._preset is None or self._rebuilding:
            return
        self._preset.overlay = OverlayConfig()
        self.set_preset(self._preset)
        self._emit_update()

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
        cfg.font_size = int(self._overlay_font_size.value())
        cfg.font_opacity = self._overlay_opacity.value()
        cfg.outline_enabled = self._overlay_outline_cb.isChecked()
        cfg.outline_width = int(self._overlay_outline_width.value())
        cfg.shadow_enabled = self._overlay_shadow_cb.isChecked()
        cfg.shadow_opacity = self._overlay_shadow_opacity.value()
        cfg.shadow_offset_x = int(self._overlay_shadow_ox.value())
        cfg.shadow_offset_y = int(self._overlay_shadow_oy.value())
        self._emit_update()

    def _on_overlay_pos_changed(self) -> None:
        """Handle title position change — sync countdown pos when linked."""
        if self._preset is None or self._rebuilding:
            return
        if self._overlay_link_cb.isChecked():
            self._overlay_countdown_x.setValue(self._overlay_title_x.value())
            self._overlay_countdown_y.setValue(self._overlay_title_y.value())
        self._on_overlay_changed()

    def _on_overlay_link_changed(self, state: int) -> None:
        """Toggle linked/independent positions for title and countdown."""
        linked = bool(state)
        self._overlay_pos_label.setText("Position:" if linked else "Title Pos:")
        self._overlay_cd_pos_label.setVisible(not linked)
        self._overlay_cd_row_widget.setVisible(not linked)

        if linked:
            self._overlay_countdown_x.setValue(self._overlay_title_x.value())
            self._overlay_countdown_y.setValue(self._overlay_title_y.value())
        self._on_overlay_changed()

    def _on_overlay_font_color_clicked(self) -> None:
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

    def _emit_update(self) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset, ChangeScope.TEXT)

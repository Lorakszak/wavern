"""Visual panel — thin coordinator for visualization, color, background, overlay sections."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.gui.panels.background_section import BackgroundSection
from wavern.gui.panels.color_section import ColorSection
from wavern.gui.panels.overlay_section import OverlaySection
from wavern.gui.panels.param_section import ParamSection
from wavern.presets.schema import Preset, VisualizationParams
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class VisualPanel(QWidget):
    """Visualization type, parameters, colors, and background settings."""

    params_changed = Signal(object)  # updated Preset
    preview_flags_changed = Signal(bool, bool)  # (skip_bg_preview, skip_overlay_preview)

    def __init__(
        self,
        parent: QWidget | None = None,
        viz_memory: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._section_states: dict[str, bool] = {}
        self._viz_memory: dict[str, dict[str, Any]] = (
            viz_memory if viz_memory is not None else {}
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = layout

        # Section widgets (created lazily in set_preset)
        self._param_section: ParamSection | None = None
        self._color_section_widget: ColorSection | None = None
        self._bg_section_widget: BackgroundSection | None = None
        self._overlay_section_widget: OverlaySection | None = None

    @property
    def preset(self) -> Preset | None:
        """The currently loaded preset, or None."""
        return self._preset

    # -- Expose internals needed by tests / dual-sidebar sync --

    @property
    def _widgets(self) -> dict[str, QWidget]:
        return self._param_section.widgets if self._param_section is not None else {}

    @property
    def _color_buttons(self) -> list:
        if self._color_section_widget is None:
            return []
        return self._color_section_widget._color_buttons

    def set_preset(self, preset: Preset) -> None:
        """Rebuild the visual panel for the given preset."""
        self._preset = preset
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

        from PySide6.QtWidgets import QFormLayout, QPushButton

        type_form_layout = QFormLayout()
        type_row = QHBoxLayout()
        type_row.addWidget(self._viz_combo, stretch=1)
        self._reset_all_btn = QPushButton("Reset All")
        self._reset_all_btn.setFixedWidth(90)
        self._reset_all_btn.clicked.connect(self._on_reset_all_params)
        type_row.addWidget(self._reset_all_btn)
        type_form_layout.addRow("Type:", type_row)
        viz_layout.addLayout(type_form_layout)

        self._param_section = ParamSection()
        self._param_section.params_changed.connect(self._on_param_changed)
        self._param_section.build(current_type, preset.visualization.params)
        viz_layout.addWidget(self._param_section)

        self._viz_section.set_content(viz_content)
        self._content_layout.addWidget(self._viz_section)

        # --- Colors ---
        self._color_section = CollapsibleSection("Colors")
        self._color_section_widget = ColorSection()
        self._color_section_widget.colors_changed.connect(self._emit_update)
        self._color_section_widget.build(preset)
        self._color_section.set_content(self._color_section_widget)
        self._content_layout.addWidget(self._color_section)

        # --- Background ---
        self._bg_section = CollapsibleSection("Background")
        self._bg_section_widget = BackgroundSection()
        self._bg_section_widget.background_changed.connect(self._emit_update)
        self._bg_section_widget.preview_flags_changed.connect(
            self._on_bg_preview_changed
        )
        self._bg_section_widget.build(preset)
        self._bg_section.set_content(self._bg_section_widget)
        self._content_layout.addWidget(self._bg_section)

        # --- Video Overlay ---
        self._overlay_section = CollapsibleSection("Video Overlay")
        self._overlay_section_widget = OverlaySection()
        self._overlay_section_widget.overlay_changed.connect(self._emit_update)
        self._overlay_section_widget.preview_flags_changed.connect(
            self._on_overlay_preview_changed
        )
        self._overlay_section_widget.build(preset)
        self._overlay_section.set_content(self._overlay_section_widget)
        self._content_layout.addWidget(self._overlay_section)

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

        # Delegate to sections
        self._param_section.update_values(preset.visualization.params)
        self._color_section_widget.update_values(preset.color_palette)
        self._bg_section_widget.update_values(preset.background)
        self._overlay_section_widget.update_values(preset.video_overlay)

        self._rebuilding = False

    def set_viz_by_index(self, index: int) -> None:
        """Switch visualization type by combo index (0-based)."""
        if self._preset is None or index >= self._viz_combo.count():
            return
        self._viz_combo.setCurrentIndex(index)

    def cycle_viz(self, reverse: bool = False) -> None:
        """Advance to the next/previous visualization type, wrapping around."""
        if self._preset is None or self._viz_combo.count() == 0:
            return
        step = -1 if reverse else 1
        next_index = (self._viz_combo.currentIndex() + step) % self._viz_combo.count()
        self._viz_combo.setCurrentIndex(next_index)

    # -- Section state persistence --

    def _save_section_states(self) -> None:
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
            "Video Overlay": "_overlay_section",
        }
        for name, attr in attr_map.items():
            if hasattr(self, attr):
                self._section_states[name] = getattr(self, attr).is_expanded()

    def _restore_section_states(self) -> None:
        attr_map = {
            "Visualization": "_viz_section",
            "Colors": "_color_section",
            "Background": "_bg_section",
            "Video Overlay": "_overlay_section",
        }
        for name, expanded in self._section_states.items():
            attr = attr_map.get(name)
            if attr and hasattr(self, attr):
                getattr(self, attr).set_expanded(expanded)

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
        self._param_section.build(new_type, restored)
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
        self._param_section.build(current_type, {})
        self._emit_update()

    def _on_param_changed(self, name: str, value: Any) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.visualization.params[name] = value
        self._emit_update()

    def _on_bg_preview_changed(self, skip_bg: bool) -> None:
        skip_overlay = (
            self._overlay_section_widget is not None
            and hasattr(self._overlay_section_widget, "_overlay_disable_preview")
            and self._overlay_section_widget._overlay_disable_preview.isChecked()
        )
        self.preview_flags_changed.emit(skip_bg, skip_overlay)

    def _on_overlay_preview_changed(self, skip_overlay: bool) -> None:
        skip_bg = (
            self._bg_section_widget is not None
            and hasattr(self._bg_section_widget, "_bg_disable_preview")
            and self._bg_section_widget._bg_disable_preview.isChecked()
        )
        self.preview_flags_changed.emit(skip_bg, skip_overlay)

    def _emit_update(self) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset)

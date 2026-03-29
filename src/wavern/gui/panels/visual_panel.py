"""Visual panel — thin coordinator for visualization, color, background, overlay sections."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.layer_list_widget import LayerListWidget
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.gui.panels.background_section import BackgroundSection
from wavern.gui.panels.color_section import ColorSection
from wavern.gui.panels.fade_section import FadeSection
from wavern.gui.change_scope import ChangeScope
from wavern.gui.panels.global_effects_section import GlobalEffectsSection
from wavern.gui.panels.overlay_section import OverlaySection
from wavern.gui.panels.param_section import ParamSection
from wavern.presets.schema import Preset, VisualizationLayer
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class VisualPanel(QWidget):
    """Visualization type, parameters, colors, and background settings."""

    params_changed = Signal(object, object)  # (Preset, ChangeScope)
    preview_flags_changed = Signal(bool, bool)  # (skip_bg_preview, skip_overlay_preview)

    def __init__(
        self,
        parent: QWidget | None = None,
        viz_memory: dict[tuple[int, str], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._viz_memory: dict[tuple[int, str], dict[str, Any]] = (
            viz_memory if viz_memory is not None else {}
        )
        self._selected_layer_index: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = layout

        from PySide6.QtWidgets import QFormLayout, QPushButton

        # --- Persistent sections (created once, never destroyed) ---

        # Layers
        self._layer_list = LayerListWidget()
        self._layer_list.layer_selected.connect(self._on_layer_selected)
        self._layer_list.layer_property_changed.connect(self._on_layer_property_changed)
        self._layer_list.layer_added.connect(self._on_layer_added)
        self._layer_list.layer_removed.connect(self._on_layer_removed)
        self._layer_list.layer_cloned.connect(self._on_layer_cloned)
        self._layer_list.layer_order_changed.connect(self._on_layer_order_changed)
        self._content_layout.addWidget(self._layer_list)

        # Visualization (type combo + params)
        self._viz_section = CollapsibleSection("Visualization", expanded=False)
        viz_content = QWidget()
        viz_layout = QVBoxLayout(viz_content)
        viz_layout.setContentsMargins(4, 0, 4, 0)

        registry = VisualizationRegistry()
        self._viz_combo = NoScrollComboBox()
        for info in registry.list_all():
            self._viz_combo.addItem(info["display_name"], info["name"])
        self._viz_combo.currentIndexChanged.connect(self._on_viz_type_changed)

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
        viz_layout.addWidget(self._param_section)

        self._viz_section.set_content(viz_content)
        self._content_layout.addWidget(self._viz_section)

        # Colors
        self._color_section = CollapsibleSection("Colors", expanded=False)
        self._color_section_widget = ColorSection()
        self._color_section_widget.colors_changed.connect(
            lambda: self._emit_update(ChangeScope.LAYER_COLORS)
        )
        self._color_section.set_content(self._color_section_widget)
        self._content_layout.addWidget(self._color_section)

        # Background
        self._bg_section = CollapsibleSection("Background", expanded=False)
        self._bg_section_widget = BackgroundSection()
        self._bg_section_widget.background_changed.connect(
            lambda: self._emit_update(ChangeScope.BACKGROUND)
        )
        self._bg_section_widget.preview_flags_changed.connect(self._on_bg_preview_changed)
        self._bg_section.set_content(self._bg_section_widget)
        self._content_layout.addWidget(self._bg_section)

        # Global Effects
        self._global_effects_section = CollapsibleSection("Global Effects", expanded=False)
        self._global_effects_widget = GlobalEffectsSection()
        self._global_effects_widget.effects_changed.connect(
            lambda: self._emit_update(ChangeScope.GLOBAL_EFFECTS)
        )
        self._global_effects_section.set_content(self._global_effects_widget)
        self._content_layout.addWidget(self._global_effects_section)

        # Video Overlay
        self._overlay_section = CollapsibleSection("Video Overlay", expanded=False)
        self._overlay_section_widget = OverlaySection()
        self._overlay_section_widget.overlay_changed.connect(
            lambda: self._emit_update(ChangeScope.OVERLAY)
        )
        self._overlay_section_widget.preview_flags_changed.connect(
            self._on_overlay_preview_changed
        )
        self._overlay_section.set_content(self._overlay_section_widget)
        self._content_layout.addWidget(self._overlay_section)

        # Fade
        self._fade_section = CollapsibleSection("Fade", expanded=False)
        self._fade_section_widget = FadeSection()
        self._fade_section_widget.fade_changed.connect(
            lambda: self._emit_update(ChangeScope.FADE)
        )
        self._fade_section.set_content(self._fade_section_widget)
        self._content_layout.addWidget(self._fade_section)

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
        """Apply a full preset (called from MainWindow._apply_preset)."""
        self.apply(preset, ChangeScope.FULL)

    def update_values(self, preset: Preset) -> None:
        """Backward-compatible alias — routes through apply with FULL scope."""
        self.apply(preset, ChangeScope.FULL)

    def apply(self, preset: Preset, scope: ChangeScope) -> None:
        """Update panel for the given preset change. Rebuilds only affected sections."""
        self._preset = preset
        self._rebuilding = True

        # Clamp selected layer index
        if self._selected_layer_index >= len(preset.layers):
            self._selected_layer_index = len(preset.layers) - 1

        if scope == ChangeScope.FULL:
            self._apply_layer_list(preset)
            self._apply_viz_and_params(preset)
            self._color_section_widget.apply(preset, self._selected_layer_index)
            self._bg_section_widget.apply(preset)
            self._global_effects_widget.apply(preset)
            self._overlay_section_widget.apply(preset)
            self._fade_section_widget.apply(preset)

        elif scope == ChangeScope.LAYER_PARAM:
            self._param_section.update_values(
                preset.layers[self._selected_layer_index].params
            )

        elif scope == ChangeScope.LAYER_COLORS:
            self._color_section_widget.apply(preset, self._selected_layer_index)

        elif scope == ChangeScope.LAYER_STRUCTURE:
            self._apply_layer_list(preset)
            self._apply_viz_and_params(preset)
            self._color_section_widget.apply(preset, self._selected_layer_index)

        elif scope in (ChangeScope.BACKGROUND, ChangeScope.BACKGROUND_EFFECTS):
            self._bg_section_widget.apply(preset)

        elif scope == ChangeScope.GLOBAL_EFFECTS:
            self._global_effects_widget.apply(preset)

        elif scope == ChangeScope.OVERLAY:
            self._overlay_section_widget.apply(preset)

        elif scope == ChangeScope.FADE:
            self._fade_section_widget.update_values(preset)

        self._rebuilding = False

    def _apply_layer_list(self, preset: Preset) -> None:
        """Update layer list with minimal widget churn."""
        self._layer_list.apply(preset.layers)
        self._layer_list.select_layer(self._selected_layer_index)

    def _apply_viz_and_params(self, preset: Preset) -> None:
        """Update viz combo + param section for the selected layer."""
        selected = self._selected_layer_index
        current_type = preset.layers[selected].visualization_type

        self._viz_combo.blockSignals(True)
        idx = self._viz_combo.findData(current_type)
        if idx >= 0:
            self._viz_combo.setCurrentIndex(idx)
        self._viz_combo.blockSignals(False)

        self._param_section.apply(current_type, preset.layers[selected].params)

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

    # -- Event handlers --

    def _on_layer_selected(self, index: int) -> None:
        """Handle selection of a layer row in the LayerListWidget.

        Args:
            index: Data-model index of the newly selected layer.
        """
        if self._preset is None or self._rebuilding:
            return
        self._selected_layer_index = index
        self._apply_viz_and_params(self._preset)
        self._color_section_widget.apply(self._preset, index)

    def _on_layer_property_changed(self, index: int, prop: str, value: object) -> None:
        """Handle blend/opacity/visibility changes from LayerListWidget.

        Args:
            index: Data-model index of the changed layer.
            prop: Property name (e.g. "blend_mode", "opacity", "visible").
            value: New property value.
        """
        if self._preset is None or self._rebuilding:
            return
        layer = self._preset.layers[index]
        self._preset.layers[index] = layer.model_copy(update={prop: value})
        self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_layer_added(self, index: int, name: str) -> None:
        """Handle a layer-added event from LayerListWidget.

        Args:
            index: Data-model index of the newly added layer (unused — we append).
            name: Auto-generated name for the new layer.
        """
        if self._preset is None or self._rebuilding:
            return
        new_layer = VisualizationLayer(visualization_type="spectrum_bars", name=name)
        self._preset.layers.append(new_layer)
        self._selected_layer_index = len(self._preset.layers) - 1
        self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_layer_removed(self, index: int) -> None:
        """Handle a layer-removed event from LayerListWidget.

        Args:
            index: Data-model index of the layer that was removed.
        """
        if self._preset is None or self._rebuilding:
            return
        if len(self._preset.layers) <= 1:
            return
        self._preset.layers.pop(index)
        if self._selected_layer_index >= len(self._preset.layers):
            self._selected_layer_index = len(self._preset.layers) - 1
        self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_layer_cloned(self, new_index: int) -> None:
        """Handle a layer-cloned event from LayerListWidget.

        The widget already inserted the cloned VisualizationLayer into its
        internal list. Mirror that insertion into the preset's layer list.

        Args:
            new_index: Data-model index of the newly created clone.
        """
        if self._preset is None or self._rebuilding:
            return
        # The widget's internal _layers already has the clone at new_index.
        cloned_layer = self._layer_list._layers[new_index]
        self._preset.layers.insert(new_index, cloned_layer)
        self._selected_layer_index = new_index
        self._apply_viz_and_params(self._preset)
        self._color_section_widget.apply(self._preset, new_index)
        self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_layer_order_changed(self, from_index: int, to_index: int) -> None:
        """Handle layer reorder from LayerListWidget.

        Args:
            from_index: Original data-model index of the moved layer.
            to_index: New data-model index after the swap.
        """
        if self._preset is None or self._rebuilding:
            return
        layers = self._preset.layers
        if 0 <= from_index < len(layers) and 0 <= to_index < len(layers):
            layers[from_index], layers[to_index] = layers[to_index], layers[from_index]
            # Follow the selection to the moved layer
            if self._selected_layer_index == from_index:
                self._selected_layer_index = to_index
            elif self._selected_layer_index == to_index:
                self._selected_layer_index = from_index
            self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_viz_type_changed(self, index: int) -> None:
        if self._preset is None or self._rebuilding:
            return
        selected = self._selected_layer_index
        old_type = self._preset.layers[selected].visualization_type
        old_params = dict(self._preset.layers[selected].params)
        self._viz_memory[(selected, old_type)] = old_params

        new_type = self._viz_combo.itemData(index)
        restored = dict(self._viz_memory.get((selected, new_type), {}))
        self._preset.layers[selected] = self._preset.layers[selected].model_copy(
            update={"visualization_type": new_type, "params": restored}
        )
        assert self._param_section is not None
        self._param_section.build(new_type, restored)
        self._emit_update(ChangeScope.LAYER_STRUCTURE)

    def _on_reset_all_params(self) -> None:
        """Reset current visualization params to schema defaults."""
        if self._preset is None or self._rebuilding:
            return
        selected = self._selected_layer_index
        current_type = self._preset.layers[selected].visualization_type
        self._viz_memory.pop((selected, current_type), None)
        self._preset.layers[selected] = self._preset.layers[selected].model_copy(
            update={"params": {}}
        )
        assert self._param_section is not None
        self._param_section.build(current_type, {})
        self._emit_update()

    def _on_param_changed(self, name: str, value: Any) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.layers[self._selected_layer_index].params[name] = value
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

    def sync_preview_flags(self, skip_bg: bool, skip_overlay: bool) -> None:
        """Sync disable-preview checkboxes from the other sidebar."""
        if self._bg_section_widget is not None and hasattr(
            self._bg_section_widget, "_bg_disable_preview"
        ):
            self._bg_section_widget._bg_disable_preview.blockSignals(True)
            self._bg_section_widget._bg_disable_preview.setChecked(skip_bg)
            self._bg_section_widget._bg_disable_preview.blockSignals(False)
        if self._overlay_section_widget is not None and hasattr(
            self._overlay_section_widget, "_overlay_disable_preview"
        ):
            self._overlay_section_widget._overlay_disable_preview.blockSignals(True)
            self._overlay_section_widget._overlay_disable_preview.setChecked(skip_overlay)
            self._overlay_section_widget._overlay_disable_preview.blockSignals(False)

    def _emit_update(self, scope: ChangeScope = ChangeScope.LAYER_PARAM) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset, scope)

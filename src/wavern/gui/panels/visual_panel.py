"""Visual panel — visualization type selector, parameter widgets, colors, background."""

import logging
from pathlib import Path
from typing import Any, Callable

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
from wavern.gui.help_button import make_help_button
from wavern.presets.schema import (
    BackgroundConfig,
    BackgroundMovement,
    ColorStop,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
    VisualizationParams,
)
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

        # --- Video Overlay ---
        self._overlay_section = CollapsibleSection("Video Overlay")
        self._build_overlay_section(preset)
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
        elif bg.type == "video" and hasattr(self, "_bg_video_label"):
            self._bg_video_label.setText(bg.video_path or "No video selected")
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

        # Update transform sub-widgets
        if hasattr(self, "_bg_rotation"):
            self._bg_rotation.blockSignals(True)
            self._bg_rotation.setValue(bg.rotation)
            self._bg_rotation.blockSignals(False)
            self._bg_mirror_x.blockSignals(True)
            self._bg_mirror_x.setChecked(bg.mirror_x)
            self._bg_mirror_x.blockSignals(False)
            self._bg_mirror_y.blockSignals(True)
            self._bg_mirror_y.setChecked(bg.mirror_y)
            self._bg_mirror_y.blockSignals(False)

        # Update movement sub-widgets
        if hasattr(self, "_mv_type_combo"):
            self._mv_type_combo.blockSignals(True)
            idx = self._mv_type_combo.findData(bg.movement.type)
            if idx >= 0:
                self._mv_type_combo.setCurrentIndex(idx)
            self._mv_type_combo.blockSignals(False)
            self._mv_speed.blockSignals(True)
            self._mv_speed.setValue(bg.movement.speed)
            self._mv_speed.blockSignals(False)
            self._mv_intensity.blockSignals(True)
            self._mv_intensity.setValue(bg.movement.intensity)
            self._mv_intensity.blockSignals(False)
            self._mv_angle.blockSignals(True)
            self._mv_angle.setValue(bg.movement.angle)
            self._mv_angle.blockSignals(False)
            self._mv_clamp.blockSignals(True)
            self._mv_clamp.setChecked(bg.movement.clamp_to_frame)
            self._mv_clamp.blockSignals(False)

        # Update overlay sub-widgets
        if hasattr(self, "_overlay_enabled"):
            ov = preset.video_overlay
            self._overlay_enabled.blockSignals(True)
            self._overlay_enabled.setChecked(ov.enabled)
            self._overlay_enabled.blockSignals(False)
            self._overlay_video_label.setText(ov.video_path or "No video selected")
            self._overlay_blend_combo.blockSignals(True)
            idx = self._overlay_blend_combo.findData(ov.blend_mode)
            if idx >= 0:
                self._overlay_blend_combo.setCurrentIndex(idx)
            self._overlay_blend_combo.blockSignals(False)
            self._overlay_opacity.blockSignals(True)
            self._overlay_opacity.setValue(ov.opacity)
            self._overlay_opacity.blockSignals(False)
            self._overlay_rotation.blockSignals(True)
            self._overlay_rotation.setValue(ov.rotation)
            self._overlay_rotation.blockSignals(False)
            self._overlay_mirror_x.blockSignals(True)
            self._overlay_mirror_x.setChecked(ov.mirror_x)
            self._overlay_mirror_x.blockSignals(False)
            self._overlay_mirror_y.blockSignals(True)
            self._overlay_mirror_y.setChecked(ov.mirror_y)
            self._overlay_mirror_y.blockSignals(False)

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
            if schema.get("disabled", False):
                widget.setEnabled(False)
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
        for bg_type in ["solid", "none", "image", "gradient", "video"]:
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
            self._build_bg_disable_preview(layout)
            self._build_transform_controls(layout, bg)
            self._build_movement_controls(layout, bg.movement)

        elif bg.type == "video":
            self._bg_video_label = QLabel(bg.video_path or "No video selected")
            self._bg_video_label.setWordWrap(True)
            pick_btn = QPushButton("Browse...")
            pick_btn.clicked.connect(self._on_bg_video_pick)
            row = QHBoxLayout()
            row.addWidget(self._bg_video_label, stretch=1)
            row.addWidget(pick_btn)
            layout.addLayout(row)

            # Video FPS info
            fps_text = ""
            if bg.video_path:
                try:
                    from wavern.core.video_source import VideoSource
                    fps = VideoSource.probe_fps(bg.video_path)
                    fps_text = f"Video FPS: {fps:.1f}"
                except Exception:
                    fps_text = "Video FPS: unknown"
            self._bg_video_fps_label = QLabel(fps_text)
            fps_help_desc = (
                "The imported video's native frame rate.\n\n"
                "If video FPS < render FPS (e.g. 30fps video at 60fps render):\n"
                "  Each video frame is shown for multiple render frames.\n"
                "  The background animates at the video's lower FPS.\n\n"
                "If video FPS > render FPS (e.g. 60fps video at 30fps render):\n"
                "  Intermediate video frames are skipped.\n"
                "  No quality loss but decode work is wasted.\n\n"
                "If they match: optimal 1:1 frame mapping.\n\n"
                "The video always plays at real-time speed synchronized\n"
                "with audio — only smoothness differs."
            )
            fps_row = QHBoxLayout()
            fps_row.addWidget(self._bg_video_fps_label, stretch=1)
            fps_row.addWidget(make_help_button(fps_help_desc))
            layout.addLayout(fps_row)

            self._build_bg_disable_preview(layout)
            self._build_transform_controls(layout, bg)
            self._build_movement_controls(layout, bg.movement)

        elif bg.type == "gradient":
            self._gradient_stop_widgets: list[dict[str, QWidget]] = []
            for i, stop in enumerate(bg.gradient_stops):
                self._add_gradient_stop_row(layout, i, stop)
            add_btn = QPushButton("+ Add Stop")
            add_btn.clicked.connect(self._on_add_gradient_stop)
            layout.addWidget(add_btn)
            self._build_bg_disable_preview(layout)
            self._build_transform_controls(layout, bg)
            self._build_movement_controls(layout, bg.movement)

    def _build_bg_disable_preview(self, layout: QVBoxLayout) -> None:
        """Add a 'Disable Preview' checkbox for the background layer."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        self._bg_disable_preview = QCheckBox()
        self._bg_disable_preview.setChecked(False)
        self._bg_disable_preview.stateChanged.connect(self._on_preview_flags_changed)
        wrapped = self._wrap_with_buttons(
            self._bg_disable_preview,
            description=(
                "Skip rendering the background in the preview.\n"
                "The background will still be included in the final export.\n"
                "Useful to save resources during editing."
            ),
            default_callback=lambda: self._bg_disable_preview.setChecked(False),
            default_label="off",
        )
        form.addRow("Disable Preview:", wrapped)
        layout.addLayout(form)

    def _on_preview_flags_changed(self) -> None:
        """Emit updated preview-skip flags when either checkbox toggles."""
        skip_bg = (
            hasattr(self, "_bg_disable_preview")
            and self._bg_disable_preview.isChecked()
        )
        skip_overlay = (
            hasattr(self, "_overlay_disable_preview")
            and self._overlay_disable_preview.isChecked()
        )
        self.preview_flags_changed.emit(skip_bg, skip_overlay)

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

    # -- Widget helpers --

    def _wrap_with_buttons(
        self,
        widget: QWidget,
        description: str = "",
        default_callback: Callable[[], None] | None = None,
        default_label: str = "",
    ) -> QWidget:
        """Wrap a widget with optional reset-to-default and help buttons."""
        if not description and default_callback is None:
            return widget
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(widget, stretch=1)
        if default_callback is not None:
            reset_btn = QPushButton("\u21BA")
            reset_btn.setObjectName("ResetButton")
            reset_btn.setFixedSize(20, 20)
            tip = f"Reset to default ({default_label})" if default_label else "Reset to default"
            reset_btn.setToolTip(tip)
            reset_btn.clicked.connect(default_callback)
            row.addWidget(reset_btn)
        if description:
            row.addWidget(make_help_button(description))
        return container

    # -- Transform controls --

    def _build_transform_controls(
        self, layout: QVBoxLayout, bg: BackgroundConfig,
    ) -> None:
        """Append rotation and mirror controls to the given layout."""
        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)

        self._bg_rotation = DragSpinBox(
            minimum=0.0, maximum=360.0, step=1.0, decimals=0,
            description="Rotates the background by the specified angle in degrees.",
            default_value=0.0,
        )
        self._bg_rotation.setValue(bg.rotation)
        self._bg_rotation.valueChanged.connect(self._on_bg_transform_changed)
        form.addRow("Rotation:", self._bg_rotation)

        self._bg_mirror_x = QCheckBox()
        self._bg_mirror_x.setChecked(bg.mirror_x)
        self._bg_mirror_x.stateChanged.connect(self._on_bg_transform_changed)
        wrapped_mx = self._wrap_with_buttons(
            self._bg_mirror_x,
            description="Flips the background horizontally.",
            default_callback=lambda: self._bg_mirror_x.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror X:", wrapped_mx)

        self._bg_mirror_y = QCheckBox()
        self._bg_mirror_y.setChecked(bg.mirror_y)
        self._bg_mirror_y.stateChanged.connect(self._on_bg_transform_changed)
        wrapped_my = self._wrap_with_buttons(
            self._bg_mirror_y,
            description="Flips the background vertically.",
            default_callback=lambda: self._bg_mirror_y.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror Y:", wrapped_my)

        layout.addLayout(form)

    def _on_bg_transform_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.background.rotation = self._bg_rotation.value()
        self._preset.background.mirror_x = self._bg_mirror_x.isChecked()
        self._preset.background.mirror_y = self._bg_mirror_y.isChecked()
        self._emit_update()

    # -- Movement controls --

    def _build_movement_controls(
        self, layout: QVBoxLayout, movement: BackgroundMovement,
    ) -> None:
        """Append background movement widgets to the given layout."""
        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)

        mv_type_desc = (
            "Animation effect applied to the background.\n\n"
            "- none: no animation\n"
            "- drift: continuous directional scroll\n"
            "- shake: pseudo-random per-frame jitter\n"
            "- wave: sinusoidal distortion\n"
            "- zoom_pulse: rhythmic zoom in/out\n"
            "- breathe: gentle slow zoom oscillation"
        )
        self._mv_type_combo = NoScrollComboBox()
        self._mv_type_combo.blockSignals(True)
        for mv_type in ["none", "drift", "shake", "wave", "zoom_pulse", "breathe"]:
            self._mv_type_combo.addItem(mv_type, mv_type)
        idx = self._mv_type_combo.findData(movement.type)
        if idx >= 0:
            self._mv_type_combo.setCurrentIndex(idx)
        self._mv_type_combo.blockSignals(False)
        self._mv_type_combo.currentIndexChanged.connect(self._on_movement_changed)
        wrapped_mv = self._wrap_with_buttons(
            self._mv_type_combo,
            description=mv_type_desc,
            default_callback=lambda: self._mv_type_combo.setCurrentIndex(0),
            default_label="none",
        )
        form.addRow("Movement:", wrapped_mv)

        self._mv_speed = DragSpinBox(
            minimum=0.0, maximum=10.0, step=0.1, decimals=1,
            description="Controls the rate of the animation effect.",
            default_value=1.0,
        )
        self._mv_speed.setValue(movement.speed)
        self._mv_speed.valueChanged.connect(self._on_movement_changed)
        form.addRow("Speed:", self._mv_speed)

        self._mv_intensity = DragSpinBox(
            minimum=0.0, maximum=2.0, step=0.05, decimals=2,
            description="Controls the magnitude of the animation effect.",
            default_value=0.5,
        )
        self._mv_intensity.setValue(movement.intensity)
        self._mv_intensity.valueChanged.connect(self._on_movement_changed)
        form.addRow("Intensity:", self._mv_intensity)

        self._mv_angle = DragSpinBox(
            minimum=0.0, maximum=360.0, step=1.0, decimals=0,
            description="Direction angle for the drift effect, in degrees.",
            default_value=0.0,
        )
        self._mv_angle.setValue(movement.angle)
        self._mv_angle.valueChanged.connect(self._on_movement_changed)
        self._mv_angle_label = QLabel("Angle:")
        form.addRow(self._mv_angle_label, self._mv_angle)

        # Clamp to frame
        clamp_desc = (
            "When enabled, prevents the movement effect from showing\n"
            "areas outside the original frame boundaries.\n\n"
            "Applies a compensating zoom and clamps coordinates\n"
            "so the background never repeats or shows empty areas."
        )
        self._mv_clamp = QCheckBox()
        self._mv_clamp.setChecked(movement.clamp_to_frame)
        self._mv_clamp.stateChanged.connect(self._on_movement_changed)
        self._mv_clamp_wrapper = self._wrap_with_buttons(
            self._mv_clamp,
            description=clamp_desc,
            default_callback=lambda: self._mv_clamp.setChecked(False),
            default_label="off",
        )
        self._mv_clamp_label = QLabel("Clamp:")
        form.addRow(self._mv_clamp_label, self._mv_clamp_wrapper)

        # Only show angle for drift; hide clamp for none/drift
        is_drift = movement.type == "drift"
        self._mv_angle.setVisible(is_drift)
        self._mv_angle_label.setVisible(is_drift)
        show_clamp = movement.type not in ("none", "drift", "shake")
        self._mv_clamp_label.setVisible(show_clamp)
        self._mv_clamp_wrapper.setVisible(show_clamp)

        layout.addLayout(form)

    def _on_movement_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        mv_type = self._mv_type_combo.currentData()
        self._preset.background.movement = BackgroundMovement(
            type=mv_type,
            speed=self._mv_speed.value(),
            intensity=self._mv_intensity.value(),
            angle=self._mv_angle.value(),
            clamp_to_frame=self._mv_clamp.isChecked(),
        )
        # Toggle angle visibility (drift only)
        is_drift = mv_type == "drift"
        self._mv_angle.setVisible(is_drift)
        self._mv_angle_label.setVisible(is_drift)
        # Toggle clamp visibility (not applicable to none/drift/shake)
        show_clamp = mv_type not in ("none", "drift", "shake")
        self._mv_clamp_label.setVisible(show_clamp)
        self._mv_clamp_wrapper.setVisible(show_clamp)
        self._emit_update()

    # -- Video Overlay section --

    def _build_overlay_section(self, preset: Preset) -> None:
        """Build the Video Overlay collapsible section."""
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(4, 0, 4, 0)

        overlay = preset.video_overlay

        self._overlay_enabled = QCheckBox()
        self._overlay_enabled.setChecked(overlay.enabled)
        self._overlay_enabled.stateChanged.connect(self._on_overlay_changed)
        wrapped_enabled = self._wrap_with_buttons(
            self._overlay_enabled,
            description="Enable video overlay compositing on top of the visualization.",
            default_callback=lambda: self._overlay_enabled.setChecked(False),
            default_label="off",
        )
        form.addRow("Enabled:", wrapped_enabled)

        self._overlay_disable_preview = QCheckBox()
        self._overlay_disable_preview.setChecked(False)
        self._overlay_disable_preview.stateChanged.connect(self._on_preview_flags_changed)
        wrapped_disable_preview = self._wrap_with_buttons(
            self._overlay_disable_preview,
            description=(
                "Skip rendering the video overlay in the preview.\n"
                "The overlay will still be included in the final export.\n"
                "Useful to save resources during editing."
            ),
            default_callback=lambda: self._overlay_disable_preview.setChecked(False),
            default_label="off",
        )
        form.addRow("Disable Preview:", wrapped_disable_preview)

        self._overlay_video_label = QLabel(overlay.video_path or "No video selected")
        self._overlay_video_label.setWordWrap(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_overlay_video_pick)
        row = QHBoxLayout()
        row.addWidget(self._overlay_video_label, stretch=1)
        row.addWidget(browse_btn)
        form.addRow("Video:", row)

        blend_desc = (
            "Controls how the overlay video blends with the scene.\n\n"
            "- alpha: standard transparency blending\n"
            "- additive: bright areas glow, black becomes transparent\n"
            "  (best for particles on black background)\n"
            "- screen: like additive but prevents over-exposure"
        )
        self._overlay_blend_combo = NoScrollComboBox()
        self._overlay_blend_combo.blockSignals(True)
        for mode in OverlayBlendMode:
            self._overlay_blend_combo.addItem(mode.value, mode)
        idx = self._overlay_blend_combo.findData(overlay.blend_mode)
        if idx >= 0:
            self._overlay_blend_combo.setCurrentIndex(idx)
        self._overlay_blend_combo.blockSignals(False)
        self._overlay_blend_combo.currentIndexChanged.connect(self._on_overlay_changed)
        wrapped_blend = self._wrap_with_buttons(
            self._overlay_blend_combo,
            description=blend_desc,
            default_callback=lambda: self._overlay_blend_combo.setCurrentIndex(
                self._overlay_blend_combo.findData(OverlayBlendMode.ADDITIVE)
            ),
            default_label="additive",
        )
        form.addRow("Blend:", wrapped_blend)

        self._overlay_opacity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
            description="Controls the transparency of the video overlay.",
            default_value=1.0,
        )
        self._overlay_opacity.setValue(overlay.opacity)
        self._overlay_opacity.valueChanged.connect(self._on_overlay_changed)
        form.addRow("Opacity:", self._overlay_opacity)

        self._overlay_rotation = DragSpinBox(
            minimum=0.0, maximum=360.0, step=1.0, decimals=0,
            description="Rotation angle in degrees applied to the overlay video.",
            default_value=0.0,
        )
        self._overlay_rotation.setValue(overlay.rotation)
        self._overlay_rotation.valueChanged.connect(self._on_overlay_changed)
        form.addRow("Rotation:", self._overlay_rotation)

        self._overlay_mirror_x = QCheckBox()
        self._overlay_mirror_x.setChecked(overlay.mirror_x)
        self._overlay_mirror_x.stateChanged.connect(self._on_overlay_changed)
        wrapped_mirror_x = self._wrap_with_buttons(
            self._overlay_mirror_x,
            description="Mirror the overlay video horizontally.",
            default_callback=lambda: self._overlay_mirror_x.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror X:", wrapped_mirror_x)

        self._overlay_mirror_y = QCheckBox()
        self._overlay_mirror_y.setChecked(overlay.mirror_y)
        self._overlay_mirror_y.stateChanged.connect(self._on_overlay_changed)
        wrapped_mirror_y = self._wrap_with_buttons(
            self._overlay_mirror_y,
            description="Mirror the overlay video vertically.",
            default_callback=lambda: self._overlay_mirror_y.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror Y:", wrapped_mirror_y)

        self._overlay_section.set_content(content)

    def _on_overlay_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.video_overlay = VideoOverlayConfig(
            enabled=self._overlay_enabled.isChecked(),
            video_path=self._preset.video_overlay.video_path,
            blend_mode=self._overlay_blend_combo.currentData(),
            opacity=self._overlay_opacity.value(),
            rotation=self._overlay_rotation.value(),
            mirror_x=self._overlay_mirror_x.isChecked(),
            mirror_y=self._overlay_mirror_y.isChecked(),
        )
        self._emit_update()

    def _on_overlay_video_pick(self) -> None:
        if self._preset is None:
            return
        default_dir = str(Path(__file__).resolve().parents[4] / "video" / "particles")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Overlay Video", default_dir,
            "Video Files (*.mp4 *.webm *.mkv *.avi *.mov)",
        )
        if path:
            self._preset.video_overlay.video_path = path
            self._overlay_video_label.setText(path)
            self._on_overlay_changed()

    def _on_bg_video_pick(self) -> None:
        if self._preset is None:
            return
        project_root = str(Path(__file__).resolve().parents[4])
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Video", project_root,
            "Video Files (*.mp4 *.webm *.mkv *.avi *.mov)",
        )
        if path:
            self._preset.background.video_path = path
            self._bg_video_label.setText(path)
            # Update FPS display
            if hasattr(self, "_bg_video_fps_label"):
                try:
                    from wavern.core.video_source import VideoSource
                    fps = VideoSource.probe_fps(path)
                    self._bg_video_fps_label.setText(f"Video FPS: {fps:.1f}")
                except Exception:
                    self._bg_video_fps_label.setText("Video FPS: unknown")
            self._emit_update()

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

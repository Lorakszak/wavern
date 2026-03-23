"""Background settings section — type, solid/gradient/image/video, transform, movement."""

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.background_picker import open_background_image
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import (
    BackgroundConfig,
    BackgroundMovement,
    ColorStop,
    Preset,
)


class BackgroundSection(QWidget):
    """Background settings: type selector, sub-widgets, transform, and movement."""

    background_changed = Signal()
    preview_flags_changed = Signal(bool)  # skip_bg

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    # -- Public API --

    def build(self, preset: Preset) -> None:
        """Build (or rebuild) the background form from a preset."""
        self._preset = preset
        self._rebuilding = True

        # Clear existing content
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

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

        self._layout.addWidget(bg_content)
        self._rebuilding = False

    def update_values(self, bg: BackgroundConfig) -> None:
        """Update widget values in-place without rebuilding."""
        self._rebuilding = True
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
                        f"background-color: {stop.color};"
                        " border: 1px solid #555;"
                    )
                    pos_spin = stop_widgets["pos_spin"]
                    pos_spin.blockSignals(True)
                    pos_spin.setValue(stop.position)
                    pos_spin.blockSignals(False)

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
        self._rebuilding = False

    # -- Internal: rebuild type-specific widgets --

    def _rebuild_bg_type_widgets(self, bg: BackgroundConfig) -> None:
        # Clear stale widget references before rebuilding. Bg types like "solid"
        # don't create transform/movement controls, so without this the old Python
        # attributes survive pointing at C++ objects destroyed by deleteLater(),
        # causing RuntimeError in update_values() when hasattr() passes.
        for _attr in (
            "_bg_color_btn", "_bg_image_label", "_bg_video_label",
            "_gradient_stop_widgets", "_bg_disable_preview",
            "_bg_rotation", "_bg_mirror_x", "_bg_mirror_y",
            "_mv_type_combo", "_mv_speed", "_mv_intensity",
            "_mv_angle", "_mv_angle_label",
            "_mv_clamp", "_mv_clamp_wrapper", "_mv_clamp_label",
        ):
            if hasattr(self, _attr):
                delattr(self, _attr)

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
            self._bg_image_label = QLabel(
                bg.image_path or "No image selected"
            )
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
            self._bg_video_label = QLabel(
                bg.video_path or "No video selected"
            )
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
                "If video FPS < render FPS "
                "(e.g. 30fps video at 60fps render):\n"
                "  Each video frame is shown for "
                "multiple render frames.\n"
                "  The background animates at the "
                "video's lower FPS.\n\n"
                "If video FPS > render FPS "
                "(e.g. 60fps video at 30fps render):\n"
                "  Intermediate video frames are skipped.\n"
                "  No quality loss but decode work is wasted.\n\n"
                "If they match: optimal 1:1 frame mapping.\n\n"
                "The video always plays at real-time speed "
                "synchronized\n"
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

    # -- Disable-preview checkbox --

    def _build_bg_disable_preview(self, layout: QVBoxLayout) -> None:
        """Add a 'Disable Preview' checkbox for the background layer."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        self._bg_disable_preview = QCheckBox()
        self._bg_disable_preview.setChecked(False)
        self._bg_disable_preview.toggled.connect(
            self._on_preview_flags_changed
        )
        wrapped = self._wrap_with_buttons(
            self._bg_disable_preview,
            description=(
                "Skip rendering the background in the preview.\n"
                "The background will still be included in the "
                "final export.\n"
                "Useful to save resources during editing."
            ),
            default_callback=(
                lambda: self._bg_disable_preview.setChecked(False)
            ),
            default_label="off",
        )
        form.addRow("Disable Preview:", wrapped)
        layout.addLayout(form)

    def _on_preview_flags_changed(self) -> None:
        """Emit updated preview-skip flag when the checkbox toggles."""
        skip_bg = (
            hasattr(self, "_bg_disable_preview")
            and self._bg_disable_preview.isChecked()
        )
        self.preview_flags_changed.emit(skip_bg)

    # -- Gradient helpers --

    def _add_gradient_stop_row(
        self, layout: QVBoxLayout, index: int, stop: ColorStop,
    ) -> None:
        row = QHBoxLayout()

        color_btn = QPushButton()
        color_btn.setFixedSize(30, 30)
        color_btn.setStyleSheet(
            f"background-color: {stop.color}; border: 1px solid #555;"
        )
        color_btn.clicked.connect(
            lambda _, idx=index: self._on_gradient_color_clicked(idx)
        )
        row.addWidget(color_btn)

        pos_spin = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
        )
        pos_spin.setValue(stop.position)
        pos_spin.valueChanged.connect(
            lambda v, idx=index: self._on_gradient_pos_changed(idx, v)
        )
        row.addWidget(pos_spin)

        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(
            lambda _, idx=index: self._on_remove_gradient_stop(idx)
        )
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
            tip = (
                f"Reset to default ({default_label})"
                if default_label
                else "Reset to default"
            )
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
            description=(
                "Rotates the background by the specified "
                "angle in degrees."
            ),
            default_value=0.0,
        )
        self._bg_rotation.setValue(bg.rotation)
        self._bg_rotation.valueChanged.connect(
            self._on_bg_transform_changed
        )
        form.addRow("Rotation:", self._bg_rotation)

        self._bg_mirror_x = QCheckBox()
        self._bg_mirror_x.setChecked(bg.mirror_x)
        self._bg_mirror_x.toggled.connect(
            self._on_bg_transform_changed
        )
        wrapped_mx = self._wrap_with_buttons(
            self._bg_mirror_x,
            description="Flips the background horizontally.",
            default_callback=lambda: self._bg_mirror_x.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror X:", wrapped_mx)

        self._bg_mirror_y = QCheckBox()
        self._bg_mirror_y.setChecked(bg.mirror_y)
        self._bg_mirror_y.toggled.connect(
            self._on_bg_transform_changed
        )
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
        self.background_changed.emit()

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
        for mv_type in [
            "none", "drift", "shake", "wave", "zoom_pulse", "breathe",
        ]:
            self._mv_type_combo.addItem(mv_type, mv_type)
        idx = self._mv_type_combo.findData(movement.type)
        if idx >= 0:
            self._mv_type_combo.setCurrentIndex(idx)
        self._mv_type_combo.blockSignals(False)
        self._mv_type_combo.currentIndexChanged.connect(
            self._on_movement_changed
        )
        wrapped_mv = self._wrap_with_buttons(
            self._mv_type_combo,
            description=mv_type_desc,
            default_callback=(
                lambda: self._mv_type_combo.setCurrentIndex(0)
            ),
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
            description=(
                "Controls the magnitude of the animation effect."
            ),
            default_value=0.5,
        )
        self._mv_intensity.setValue(movement.intensity)
        self._mv_intensity.valueChanged.connect(
            self._on_movement_changed
        )
        form.addRow("Intensity:", self._mv_intensity)

        self._mv_angle = DragSpinBox(
            minimum=0.0, maximum=360.0, step=1.0, decimals=0,
            description=(
                "Direction angle for the drift effect, in degrees."
            ),
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
        self._mv_clamp.toggled.connect(self._on_movement_changed)
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
        self.background_changed.emit()

    # -- Event handlers --

    def _on_bg_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.background.type = self._bg_type_combo.currentData()
        self._rebuild_bg_type_widgets(self._preset.background)
        self.background_changed.emit()

    def _on_bg_image_pick(self) -> None:
        if self._preset is None:
            return
        path = open_background_image(self)
        if path is not None:
            self._preset.background.image_path = str(path)
            self._bg_image_label.setText(str(path))
            self.background_changed.emit()

    def _on_bg_video_pick(self) -> None:
        if self._preset is None:
            return
        default_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Video", default_dir,
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
                    self._bg_video_fps_label.setText(
                        f"Video FPS: {fps:.1f}"
                    )
                except Exception:
                    self._bg_video_fps_label.setText(
                        "Video FPS: unknown"
                    )
            self.background_changed.emit()

    def _on_bg_color_clicked(self) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        current = QColor(self._preset.background.color)
        color = QColorDialog.getColor(
            current, self, "Background Color"
        )
        if color.isValid():
            hex_color = color.name().upper()
            self._preset.background.color = hex_color
            self._bg_color_btn.setStyleSheet(
                f"background-color: {hex_color};"
                " border: 1px solid #555;"
            )
            self.background_changed.emit()

    def _on_gradient_color_clicked(self, index: int) -> None:
        if self._preset is None:
            return
        from PySide6.QtGui import QColor

        stops = self._preset.background.gradient_stops
        if index >= len(stops):
            return
        current = QColor(stops[index].color)
        color = QColorDialog.getColor(
            current, self, "Gradient Stop Color"
        )
        if color.isValid():
            hex_color = color.name().upper()
            stops[index].color = hex_color
            self._gradient_stop_widgets[index]["color_btn"].setStyleSheet(
                f"background-color: {hex_color};"
                " border: 1px solid #555;"
            )
            self.background_changed.emit()

    def _on_gradient_pos_changed(
        self, index: int, value: float,
    ) -> None:
        if self._preset is None or self._rebuilding:
            return
        stops = self._preset.background.gradient_stops
        if index < len(stops):
            stops[index].position = value
            self.background_changed.emit()

    def _on_add_gradient_stop(self) -> None:
        if self._preset is None:
            return
        self._preset.background.gradient_stops.append(
            ColorStop(position=0.5, color="#808080")
        )
        self._rebuild_bg_type_widgets(self._preset.background)
        self.background_changed.emit()

    def _on_remove_gradient_stop(self, index: int) -> None:
        if self._preset is None:
            return
        stops = self._preset.background.gradient_stops
        if len(stops) <= 2:
            return
        stops.pop(index)
        self._rebuild_bg_type_widgets(self._preset.background)
        self.background_changed.emit()

"""Background settings section — type, solid/gradient/image/video, transform, movement."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

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
    AudioReactiveConfig,
    BackgroundConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
    BackgroundMovements,
    ColorStop,
    Preset,
)


class BackgroundSection(QWidget):
    """Background settings: type selector, sub-widgets, transform, and movement."""

    background_changed = Signal()
    preview_flags_changed = Signal(bool)  # skip_bg

    # Background types that show transform/effects sections
    _RICH_BG_TYPES = frozenset({"image", "video", "gradient"})
    # Background types that support movement (gradient is 1D texture, movements don't apply)
    _MOVEMENT_BG_TYPES = frozenset({"image", "video"})

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._current_bg_type: str | None = None
        # Persistent shared sections (built once in build(), reused across type switches)
        self._shared_sections_built: bool = False
        self._disable_preview_container: QWidget | None = None
        self._transform_container: QWidget | None = None
        self._movement_container: QWidget | None = None
        self._effects_container: QWidget | None = None

    # -- Public API --

    def build(self, preset: Preset) -> None:
        """Build (or rebuild) the background form from a preset."""
        self._preset = preset
        self._rebuilding = True

        # Clear existing content
        while self._layout.count():
            item = self._layout.takeAt(0)
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

        self._shared_sections_built = False

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

        # Build persistent shared sections (disable-preview, transform, movement, effects)
        # These are created once and shown/hidden based on background type.
        bg = preset.background
        self._build_shared_sections(bg)

        self._rebuild_bg_type_widgets(bg)

        self._layout.addWidget(bg_content)
        self._current_bg_type = preset.background.type
        self._rebuilding = False

    def _build_shared_sections(self, bg: BackgroundConfig) -> None:
        """Build the persistent disable-preview, transform, movement, and effects sections."""
        layout = self._bg_layout

        # Disable preview
        self._disable_preview_container = QWidget()
        dp_layout = QVBoxLayout(self._disable_preview_container)
        dp_layout.setContentsMargins(0, 0, 0, 0)
        self._build_bg_disable_preview(dp_layout)
        layout.addRow(self._disable_preview_container)

        # Transform
        self._transform_container = QWidget()
        tr_layout = QVBoxLayout(self._transform_container)
        tr_layout.setContentsMargins(0, 0, 0, 0)
        self._build_transform_controls(tr_layout, bg)
        layout.addRow(self._transform_container)

        # Movement
        self._movement_container = QWidget()
        mv_layout = QVBoxLayout(self._movement_container)
        mv_layout.setContentsMargins(0, 0, 0, 0)
        self._build_movement_controls(mv_layout, bg.movements)
        layout.addRow(self._movement_container)

        # Effects (always visible — solid/none also get effects)
        self._effects_container = QWidget()
        fx_layout = QVBoxLayout(self._effects_container)
        fx_layout.setContentsMargins(0, 0, 0, 0)
        self._build_effects_controls(fx_layout, bg.effects)
        layout.addRow(self._effects_container)

        self._shared_sections_built = True
        self._sync_shared_section_visibility(bg.type)

    def update_values(self, bg: BackgroundConfig, preset: Preset | None = None) -> None:
        """Update widget values in-place without rebuilding."""
        if preset is not None:
            self._preset = preset
        self._rebuilding = True

        # Type-specific widget values
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
                    pos_spin = cast(DragSpinBox, stop_widgets["pos_spin"])
                    pos_spin.blockSignals(True)
                    pos_spin.setValue(stop.position)
                    pos_spin.blockSignals(False)

        # Persistent shared section values
        self._update_shared_section_values(bg)
        self._rebuilding = False

    def _sync_shared_section_visibility(self, bg_type: str) -> None:
        """Show/hide the persistent shared sections based on background type."""
        is_rich = bg_type in self._RICH_BG_TYPES
        if self._disable_preview_container is not None:
            self._disable_preview_container.setVisible(is_rich)
        if self._transform_container is not None:
            self._transform_container.setVisible(is_rich)
        if self._movement_container is not None:
            self._movement_container.setVisible(bg_type in self._MOVEMENT_BG_TYPES)
        # Effects are always visible (solid/none also support effects)
        if self._effects_container is not None:
            self._effects_container.setVisible(True)

    def apply(self, preset: Preset) -> None:
        """Update in-place if bg type unchanged, otherwise rebuild."""
        if preset.background.type == self._current_bg_type and self._current_bg_type is not None:
            self.update_values(preset.background, preset)
        else:
            if self._shared_sections_built:
                # Shared sections persist — only rebuild type-specific widgets
                self._preset = preset
                self._rebuilding = True
                # Sync the type combo to match the new type
                self._bg_type_combo.blockSignals(True)
                idx = self._bg_type_combo.findData(preset.background.type)
                if idx >= 0:
                    self._bg_type_combo.setCurrentIndex(idx)
                self._bg_type_combo.blockSignals(False)
                self._rebuild_bg_type_widgets(preset.background)
                self._sync_shared_section_visibility(preset.background.type)
                self._update_shared_section_values(preset.background)
                self._current_bg_type = preset.background.type
                self._rebuilding = False
            else:
                self.build(preset)

    # -- Internal: rebuild type-specific widgets --

    def _rebuild_bg_type_widgets(self, bg: BackgroundConfig) -> None:
        """Rebuild only the type-specific content (color/image/video/gradient picker).

        The shared sections (disable-preview, transform, movement, effects) are
        persistent — built once in _build_shared_sections() and shown/hidden here.
        """
        # Clear stale type-specific widget references
        for _attr in (
            "_bg_color_btn",
            "_bg_image_label",
            "_bg_video_label",
            "_bg_video_fps_label",
            "_gradient_stop_widgets",
        ):
            if hasattr(self, _attr):
                delattr(self, _attr)

        layout = self._bg_type_container_layout
        while layout.count():
            item = layout.takeAt(0)
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

        elif bg.type == "none":
            pass  # No type-specific widgets

        elif bg.type == "image":
            self._bg_image_label = QLabel(bg.image_path or "No image selected")
            self._bg_image_label.setWordWrap(True)
            pick_btn = QPushButton("Browse...")
            pick_btn.clicked.connect(self._on_bg_image_pick)
            row = QHBoxLayout()
            row.addWidget(self._bg_image_label, stretch=1)
            row.addWidget(pick_btn)
            layout.addLayout(row)

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

        elif bg.type == "gradient":
            self._gradient_stop_widgets: list[dict[str, QWidget]] = []
            for i, stop in enumerate(bg.gradient_stops):
                self._add_gradient_stop_row(layout, i, stop)
            add_btn = QPushButton("+ Add Stop")
            add_btn.clicked.connect(self._on_add_gradient_stop)
            layout.addWidget(add_btn)

        # Update visibility of persistent shared sections
        self._sync_shared_section_visibility(bg.type)

    def _update_shared_section_values(self, bg: BackgroundConfig) -> None:
        """Sync persistent shared section widget values with the current preset."""
        # Transform
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

        # Movement
        for mv_name in ("drift", "shake", "wave", "zoom_pulse", "breathe"):
            enable_cb = getattr(self, f"_mv_{mv_name}_enable", None)
            if enable_cb is None:
                continue
            mv: BackgroundMovement = getattr(bg.movements, mv_name)
            enable_cb.blockSignals(True)
            enable_cb.setChecked(mv.enabled)
            enable_cb.blockSignals(False)
            sub = getattr(self, f"_mv_{mv_name}_sub", None)
            if sub is not None:
                sub.setVisible(mv.enabled)
            for field, attr_suffix in (
                ("speed", "speed"), ("intensity", "intensity"), ("angle", "angle"),
            ):
                spin = getattr(self, f"_mv_{mv_name}_{attr_suffix}")
                spin.blockSignals(True)
                spin.setValue(getattr(mv, field))
                spin.blockSignals(False)
            clamp_cb = getattr(self, f"_mv_{mv_name}_clamp")
            clamp_cb.blockSignals(True)
            clamp_cb.setChecked(mv.clamp_to_frame)
            clamp_cb.blockSignals(False)
            # Audio reactive
            self._sync_audio_controls(f"_mv_{mv_name}", mv.audio)

        # Effects
        for attr_name in ("blur", "hue_shift", "saturation", "brightness",
                          "pixelate", "posterize", "invert"):
            enable_cb = getattr(self, f"_fx_{attr_name}_enable", None)
            if enable_cb is None:
                continue
            effect = getattr(bg.effects, attr_name)
            enable_cb.blockSignals(True)
            enable_cb.setChecked(effect.enabled)
            enable_cb.blockSignals(False)
            sub = getattr(self, f"_fx_{attr_name}_sub", None)
            if sub is not None:
                sub.setVisible(effect.enabled)
            intensity_spin = getattr(self, f"_fx_{attr_name}_intensity")
            intensity_spin.blockSignals(True)
            intensity_spin.setValue(effect.intensity)
            intensity_spin.blockSignals(False)
            # Audio reactive
            self._sync_audio_controls(f"_fx_{attr_name}", effect.audio)

    def _sync_audio_controls(self, prefix: str, audio: AudioReactiveConfig) -> None:
        """Sync audio reactive widget values for a given prefix."""
        audio_cb = getattr(self, f"{prefix}_audio_cb", None)
        if audio_cb is None:
            return
        audio_cb.blockSignals(True)
        audio_cb.setChecked(audio.enabled)
        audio_cb.blockSignals(False)
        audio_source_label = getattr(self, f"{prefix}_audio_source_label", None)
        if audio_source_label is not None:
            audio_source_label.setVisible(audio.enabled)
        audio_source = getattr(self, f"{prefix}_audio_source", None)
        if audio_source is not None:
            audio_source.blockSignals(True)
            audio_source.setVisible(audio.enabled)
            idx = audio_source.findData(audio.source)
            if idx >= 0:
                audio_source.setCurrentIndex(idx)
            audio_source.blockSignals(False)
        audio_sensitivity = getattr(self, f"{prefix}_audio_sensitivity", None)
        if audio_sensitivity is not None:
            audio_sensitivity.blockSignals(True)
            audio_sensitivity.setValue(audio.sensitivity)
            audio_sensitivity.blockSignals(False)
        audio_sens_wrapper = getattr(self, f"{prefix}_audio_sens_wrapper", None)
        if audio_sens_wrapper is not None:
            audio_sens_wrapper.setVisible(audio.enabled)

    # -- Disable-preview checkbox --

    def _build_bg_disable_preview(self, layout: QVBoxLayout) -> None:
        """Add a 'Disable Preview' checkbox for the background layer."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        self._bg_disable_preview = QCheckBox()
        self._bg_disable_preview.setChecked(False)
        self._bg_disable_preview.toggled.connect(self._on_preview_flags_changed)
        wrapped = self._wrap_with_buttons(
            self._bg_disable_preview,
            description=(
                "Skip rendering the background in the preview.\n"
                "The background will still be included in the "
                "final export.\n"
                "Useful to save resources during editing."
            ),
            default_callback=(lambda: self._bg_disable_preview.setChecked(False)),
            default_label="off",
        )
        form.addRow("Disable Preview:", wrapped)
        layout.addLayout(form)

    def _on_preview_flags_changed(self) -> None:
        """Emit updated preview-skip flag when the checkbox toggles."""
        skip_bg = hasattr(self, "_bg_disable_preview") and self._bg_disable_preview.isChecked()
        self.preview_flags_changed.emit(skip_bg)

    # -- Gradient helpers --

    def _add_gradient_stop_row(
        self,
        layout: QVBoxLayout,
        index: int,
        stop: ColorStop,
    ) -> None:
        row = QHBoxLayout()

        color_btn = QPushButton()
        color_btn.setFixedSize(30, 30)
        color_btn.setStyleSheet(f"background-color: {stop.color}; border: 1px solid #555;")
        color_btn.clicked.connect(lambda _, idx=index: self._on_gradient_color_clicked(idx))
        row.addWidget(color_btn)

        pos_spin = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
        )
        pos_spin.setValue(stop.position)
        pos_spin.valueChanged.connect(lambda v, idx=index: self._on_gradient_pos_changed(idx, v))
        row.addWidget(pos_spin)

        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda _, idx=index: self._on_remove_gradient_stop(idx))
        row.addWidget(remove_btn)

        layout.addLayout(row)
        self._gradient_stop_widgets.append({"color_btn": color_btn, "pos_spin": pos_spin})

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
            reset_btn = QPushButton("\u21ba")
            reset_btn.setObjectName("ResetButton")
            reset_btn.setFixedSize(20, 20)
            tip = f"Reset to default ({default_label})" if default_label else "Reset to default"
            reset_btn.setToolTip(tip)
            reset_btn.clicked.connect(default_callback)
            row.addWidget(reset_btn)
        if description:
            row.addWidget(make_help_button(description))
        return container

    def _build_audio_reactive_controls(
        self,
        form: QFormLayout,
        audio: AudioReactiveConfig,
        prefix: str,
        on_changed: Callable[[], None],
    ) -> tuple[QCheckBox, NoScrollComboBox, DragSpinBox, QLabel, QWidget]:
        """Build audio-reactive controls: checkbox, source combo, sensitivity.

        Args:
            form: Layout to add rows to.
            audio: Current audio reactive config.
            prefix: Attribute prefix for storing widget references.
            on_changed: Callback when any value changes.

        Returns:
            (reactive_cb, source_combo, sensitivity_spin, source_label, sensitivity_wrapper)
        """
        reactive_cb = QCheckBox()
        reactive_cb.setChecked(audio.enabled)
        reactive_cb.toggled.connect(on_changed)
        wrapped_reactive = self._wrap_with_buttons(
            reactive_cb,
            description=(
                "When enabled, the effect intensity is modulated\n"
                "by the selected audio signal in real time."
            ),
            default_callback=lambda: reactive_cb.setChecked(False),
            default_label="off",
        )
        form.addRow("Audio Reactive:", wrapped_reactive)

        source_combo = NoScrollComboBox()
        source_combo.blockSignals(True)
        for source in ("amplitude", "bass", "beat", "mid", "treble"):
            source_combo.addItem(source, source)
        idx = source_combo.findData(audio.source)
        if idx >= 0:
            source_combo.setCurrentIndex(idx)
        source_combo.blockSignals(False)
        source_combo.currentIndexChanged.connect(on_changed)
        source_label = QLabel("Audio Source:")
        form.addRow(source_label, source_combo)

        sensitivity_spin = DragSpinBox(
            minimum=0.1,
            maximum=5.0,
            step=0.1,
            decimals=1,
            description="Multiplier for the audio signal strength.",
            default_value=1.0,
        )
        sensitivity_spin.setValue(audio.sensitivity)
        sensitivity_spin.valueChanged.connect(on_changed)
        sens_wrapper = self._wrap_with_buttons(
            sensitivity_spin,
            description="Multiplier for the audio signal strength.",
            default_callback=lambda: sensitivity_spin.setValue(1.0),
            default_label="1.0",
        )
        sens_label = QLabel("Sensitivity:")
        form.addRow(sens_label, sens_wrapper)

        # Show/hide source and sensitivity based on reactive checkbox
        source_label.setVisible(audio.enabled)
        source_combo.setVisible(audio.enabled)
        sens_label.setVisible(audio.enabled)
        sens_wrapper.setVisible(audio.enabled)

        def _toggle_audio_visibility(checked: bool) -> None:
            source_label.setVisible(checked)
            source_combo.setVisible(checked)
            sens_label.setVisible(checked)
            sens_wrapper.setVisible(checked)

        reactive_cb.toggled.connect(_toggle_audio_visibility)

        return reactive_cb, source_combo, sensitivity_spin, source_label, sens_wrapper

    # -- Transform controls --

    def _build_transform_controls(
        self,
        layout: QVBoxLayout,
        bg: BackgroundConfig,
    ) -> None:
        """Append rotation and mirror controls to the given layout."""
        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)

        self._bg_rotation = DragSpinBox(
            minimum=0.0,
            maximum=360.0,
            step=1.0,
            decimals=0,
            description=("Rotates the background by the specified angle in degrees."),
            default_value=0.0,
        )
        self._bg_rotation.setValue(bg.rotation)
        self._bg_rotation.valueChanged.connect(self._on_bg_transform_changed)
        form.addRow("Rotation:", self._bg_rotation)

        self._bg_mirror_x = QCheckBox()
        self._bg_mirror_x.setChecked(bg.mirror_x)
        self._bg_mirror_x.toggled.connect(self._on_bg_transform_changed)
        wrapped_mx = self._wrap_with_buttons(
            self._bg_mirror_x,
            description="Flips the background horizontally.",
            default_callback=lambda: self._bg_mirror_x.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror X:", wrapped_mx)

        self._bg_mirror_y = QCheckBox()
        self._bg_mirror_y.setChecked(bg.mirror_y)
        self._bg_mirror_y.toggled.connect(self._on_bg_transform_changed)
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
        self,
        layout: QVBoxLayout,
        movements: BackgroundMovements,
    ) -> None:
        """Append per-movement-type controls to the given layout."""
        header = QLabel("Movement")
        header.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(header)

        movement_items: list[tuple[str, str, BackgroundMovement]] = [
            ("drift", "Drift", movements.drift),
            ("shake", "Shake", movements.shake),
            ("wave", "Wave", movements.wave),
            ("zoom_pulse", "Zoom Pulse", movements.zoom_pulse),
            ("breathe", "Breathe", movements.breathe),
        ]

        for attr_name, display_name, movement in movement_items:
            self._build_single_movement(layout, attr_name, display_name, movement)

    def _build_single_movement(
        self,
        layout: QVBoxLayout,
        attr_name: str,
        display_name: str,
        movement: BackgroundMovement,
    ) -> None:
        """Build controls for a single movement type."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        # Enable checkbox — always visible
        enable_cb = QCheckBox(display_name)
        enable_cb.setChecked(movement.enabled)
        enable_cb.toggled.connect(self._on_movement_changed)
        form.addRow(enable_cb)

        # Sub-controls container — shown/hidden by enable checkbox
        sub_container = QWidget()
        sub_layout = QFormLayout(sub_container)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        # Speed
        speed_spin = DragSpinBox(
            minimum=0.0,
            maximum=10.0,
            step=0.1,
            decimals=1,
            description=f"Controls the rate of the {display_name.lower()} animation.",
            default_value=1.0,
        )
        speed_spin.setValue(movement.speed)
        speed_spin.valueChanged.connect(self._on_movement_changed)
        sub_layout.addRow("Speed:", speed_spin)

        # Intensity
        intensity_spin = DragSpinBox(
            minimum=0.0,
            maximum=2.0,
            step=0.05,
            decimals=2,
            description=f"Controls the magnitude of the {display_name.lower()} animation.",
            default_value=0.5,
        )
        intensity_spin.setValue(movement.intensity)
        intensity_spin.valueChanged.connect(self._on_movement_changed)
        sub_layout.addRow("Intensity:", intensity_spin)

        # Angle — only for drift
        angle_spin = DragSpinBox(
            minimum=0.0,
            maximum=360.0,
            step=1.0,
            decimals=0,
            description="Direction angle for the drift effect, in degrees.",
            default_value=0.0,
        )
        angle_spin.setValue(movement.angle)
        angle_spin.valueChanged.connect(self._on_movement_changed)
        angle_label = QLabel("Angle:")
        is_drift = attr_name == "drift"
        angle_label.setVisible(is_drift)
        angle_spin.setVisible(is_drift)
        sub_layout.addRow(angle_label, angle_spin)

        # Clamp — not for drift
        clamp_cb = QCheckBox()
        clamp_cb.setChecked(movement.clamp_to_frame)
        clamp_cb.toggled.connect(self._on_movement_changed)
        clamp_label = QLabel("Clamp:")
        clamp_label.setVisible(not is_drift)
        clamp_cb.setVisible(not is_drift)
        sub_layout.addRow(clamp_label, clamp_cb)

        # Audio reactive
        (
            audio_cb,
            audio_source,
            audio_sensitivity,
            audio_source_label,
            audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            movement.audio,
            f"mv_{attr_name}",
            self._on_movement_changed,
        )

        sub_container.setVisible(movement.enabled)
        enable_cb.toggled.connect(sub_container.setVisible)

        form.addRow(sub_container)
        layout.addLayout(form)

        # Store widget references
        setattr(self, f"_mv_{attr_name}_enable", enable_cb)
        setattr(self, f"_mv_{attr_name}_speed", speed_spin)
        setattr(self, f"_mv_{attr_name}_intensity", intensity_spin)
        setattr(self, f"_mv_{attr_name}_angle", angle_spin)
        setattr(self, f"_mv_{attr_name}_angle_label", angle_label)
        setattr(self, f"_mv_{attr_name}_clamp", clamp_cb)
        setattr(self, f"_mv_{attr_name}_clamp_label", clamp_label)
        setattr(self, f"_mv_{attr_name}_sub", sub_container)
        setattr(self, f"_mv_{attr_name}_audio_cb", audio_cb)
        setattr(self, f"_mv_{attr_name}_audio_source", audio_source)
        setattr(self, f"_mv_{attr_name}_audio_sensitivity", audio_sensitivity)
        setattr(self, f"_mv_{attr_name}_audio_source_label", audio_source_label)
        setattr(self, f"_mv_{attr_name}_audio_sens_wrapper", audio_sens_wrapper)

    def _on_movement_changed(self) -> None:
        """Collect movement widget values into the preset and emit signal."""
        if self._preset is None or self._rebuilding:
            return

        for attr_name in ("drift", "shake", "wave", "zoom_pulse", "breathe"):
            enable_cb = getattr(self, f"_mv_{attr_name}_enable", None)
            speed_spin = getattr(self, f"_mv_{attr_name}_speed", None)
            intensity_spin = getattr(self, f"_mv_{attr_name}_intensity", None)
            angle_spin = getattr(self, f"_mv_{attr_name}_angle", None)
            clamp_cb = getattr(self, f"_mv_{attr_name}_clamp", None)
            audio_cb = getattr(self, f"_mv_{attr_name}_audio_cb", None)
            audio_source = getattr(self, f"_mv_{attr_name}_audio_source", None)
            audio_sensitivity = getattr(self, f"_mv_{attr_name}_audio_sensitivity", None)

            if (
                enable_cb is None
                or speed_spin is None
                or intensity_spin is None
                or angle_spin is None
                or clamp_cb is None
                or audio_cb is None
                or audio_source is None
                or audio_sensitivity is None
            ):
                continue

            audio = AudioReactiveConfig(
                enabled=audio_cb.isChecked(),
                source=audio_source.currentData() or "amplitude",
                sensitivity=audio_sensitivity.value(),
            )
            mv = BackgroundMovement(
                enabled=enable_cb.isChecked(),
                speed=speed_spin.value(),
                intensity=intensity_spin.value(),
                angle=angle_spin.value(),
                clamp_to_frame=clamp_cb.isChecked(),
                audio=audio,
            )
            setattr(self._preset.background.movements, attr_name, mv)

        self.background_changed.emit()

    # -- Effects controls --

    def _build_effects_controls(
        self,
        layout: QVBoxLayout,
        effects: BackgroundEffects,
    ) -> None:
        """Append background effects widgets to the given layout."""
        header = QLabel("Effects")
        header.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(header)

        effect_items: list[tuple[str, str, BackgroundEffect]] = [
            ("blur", "Blur", effects.blur),
            ("hue_shift", "Hue Shift", effects.hue_shift),
            ("saturation", "Saturation", effects.saturation),
            ("brightness", "Brightness", effects.brightness),
            ("pixelate", "Pixelate", effects.pixelate),
            ("posterize", "Posterize", effects.posterize),
            ("invert", "Invert", effects.invert),
        ]

        for attr_name, display_name, effect in effect_items:
            self._build_single_effect(layout, attr_name, display_name, effect)

    def _build_single_effect(
        self,
        layout: QVBoxLayout,
        attr_name: str,
        display_name: str,
        effect: BackgroundEffect,
    ) -> None:
        """Build controls for a single effect."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        # Enable checkbox — always visible
        enable_cb = QCheckBox(display_name)
        enable_cb.setChecked(effect.enabled)
        enable_cb.toggled.connect(self._on_effects_changed)
        form.addRow(enable_cb)

        # Sub-controls container — shown/hidden by enable checkbox
        sub_container = QWidget()
        sub_layout = QFormLayout(sub_container)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        # Intensity
        intensity_spin = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description=f"Controls the strength of the {display_name.lower()} effect.",
            default_value=0.5,
        )
        intensity_spin.setValue(effect.intensity)
        intensity_spin.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", intensity_spin)

        # Audio reactive controls (added to sub_layout)
        (
            audio_cb,
            audio_source,
            audio_sensitivity,
            audio_source_label,
            audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            f"fx_{attr_name}",
            self._on_effects_changed,
        )

        sub_container.setVisible(effect.enabled)
        enable_cb.toggled.connect(sub_container.setVisible)

        form.addRow(sub_container)
        layout.addLayout(form)

        # Store references for update_values and _on_effects_changed
        setattr(self, f"_fx_{attr_name}_enable", enable_cb)
        setattr(self, f"_fx_{attr_name}_intensity", intensity_spin)
        setattr(self, f"_fx_{attr_name}_sub", sub_container)
        setattr(self, f"_fx_{attr_name}_audio_cb", audio_cb)
        setattr(self, f"_fx_{attr_name}_audio_source", audio_source)
        setattr(self, f"_fx_{attr_name}_audio_sensitivity", audio_sensitivity)
        setattr(self, f"_fx_{attr_name}_audio_source_label", audio_source_label)
        setattr(self, f"_fx_{attr_name}_audio_sens_wrapper", audio_sens_wrapper)

    def _on_effects_changed(self) -> None:
        """Collect effect widget values into the preset and emit signal."""
        if self._preset is None or self._rebuilding:
            return

        for attr_name in (
            "blur",
            "hue_shift",
            "saturation",
            "brightness",
            "pixelate",
            "posterize",
            "invert",
        ):
            enable_cb = getattr(self, f"_fx_{attr_name}_enable", None)
            intensity_spin = getattr(self, f"_fx_{attr_name}_intensity", None)
            audio_cb = getattr(self, f"_fx_{attr_name}_audio_cb", None)
            audio_source = getattr(self, f"_fx_{attr_name}_audio_source", None)
            audio_sensitivity = getattr(self, f"_fx_{attr_name}_audio_sensitivity", None)

            if (
                enable_cb is None
                or intensity_spin is None
                or audio_cb is None
                or audio_source is None
                or audio_sensitivity is None
            ):
                continue

            effect = BackgroundEffect(
                enabled=enable_cb.isChecked(),
                intensity=intensity_spin.value(),
                audio=AudioReactiveConfig(
                    enabled=audio_cb.isChecked(),
                    source=audio_source.currentData() or "amplitude",
                    sensitivity=audio_sensitivity.value(),
                ),
            )
            setattr(self._preset.background.effects, attr_name, effect)

        self.background_changed.emit()

    # -- Event handlers --

    def _on_bg_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.background.type = self._bg_type_combo.currentData()
        self._rebuilding = True
        self._rebuild_bg_type_widgets(self._preset.background)
        self._current_bg_type = self._preset.background.type
        self._rebuilding = False
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
            self,
            "Select Background Video",
            default_dir,
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
            self.background_changed.emit()

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
            self.background_changed.emit()

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
            self.background_changed.emit()

    def _on_gradient_pos_changed(
        self,
        index: int,
        value: float,
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
        self._preset.background.gradient_stops.append(ColorStop(position=0.5, color="#808080"))
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

"""Global post-processing effects section — vignette, chromatic aberration, glitch, film grain."""

import logging
from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import (
    AudioReactiveConfig,
    BloomEffect,
    ChromaticAberrationEffect,
    ColorShiftEffect,
    FilmGrainEffect,
    GlitchEffect,
    Preset,
    ScanlinesEffect,
    VignetteEffect,
)

logger = logging.getLogger(__name__)


class GlobalEffectsSection(QWidget):
    """Controls for global post-processing effects applied to the composited frame."""

    effects_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._built: bool = False

    def build(self, preset: Preset) -> None:
        """Build the global effects UI for the given preset."""
        self._preset = preset
        self._rebuilding = True

        # Clear existing content from the wrapper layout
        while self._layout.count():
            item = self._layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 0, 4, 0)

        effects = preset.global_effects

        # Apply stage combo
        stage_form = QFormLayout()
        self._stage_combo = NoScrollComboBox()
        self._stage_combo.blockSignals(True)
        self._stage_combo.addItem("Before Overlays", "before_overlays")
        self._stage_combo.addItem("After Overlays", "after_overlays")
        idx = self._stage_combo.findData(effects.apply_stage)
        if idx >= 0:
            self._stage_combo.setCurrentIndex(idx)
        self._stage_combo.blockSignals(False)
        self._stage_combo.currentIndexChanged.connect(self._on_effects_changed)
        stage_form.addRow("Apply:", self._stage_combo)
        layout.addLayout(stage_form)

        # Vignette
        self._build_vignette(layout, effects.vignette)

        # Chromatic Aberration
        self._build_chromatic(layout, effects.chromatic_aberration)

        # Glitch
        self._build_glitch(layout, effects.glitch)

        # Film Grain
        self._build_film_grain(layout, effects.film_grain)

        # Bloom
        self._build_bloom(layout, effects.bloom)

        # Scanlines
        self._build_scanlines(layout, effects.scanlines)

        # Color Shift
        self._build_color_shift(layout, effects.color_shift)

        self._layout.addWidget(content)
        self._built = True
        self._rebuilding = False

    def _build_vignette(self, layout: QVBoxLayout, effect: VignetteEffect) -> None:
        """Build vignette controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._vignette_enable = QCheckBox("Vignette")
        self._vignette_enable.setChecked(effect.enabled)
        self._vignette_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._vignette_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._vignette_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls how far inward the darkening reaches.",
            default_value=0.5,
        )
        self._vignette_intensity.setValue(effect.intensity)
        self._vignette_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._vignette_intensity)

        self._vignette_shape = NoScrollComboBox()
        self._vignette_shape.blockSignals(True)
        for shape_name, shape_val in [
            ("Circular", "circular"),
            ("Rectangular", "rectangular"),
            ("Diamond", "diamond"),
        ]:
            self._vignette_shape.addItem(shape_name, shape_val)
        idx = self._vignette_shape.findData(effect.shape)
        if idx >= 0:
            self._vignette_shape.setCurrentIndex(idx)
        self._vignette_shape.blockSignals(False)
        self._vignette_shape.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Shape:", self._vignette_shape)

        (
            self._vignette_audio_cb,
            self._vignette_audio_source,
            self._vignette_audio_sensitivity,
            self._vignette_audio_source_label,
            self._vignette_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._vignette_sub = sub
        sub.setVisible(effect.enabled)
        self._vignette_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_chromatic(
        self,
        layout: QVBoxLayout,
        effect: ChromaticAberrationEffect,
    ) -> None:
        """Build chromatic aberration controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._chromatic_enable = QCheckBox("Chromatic Aberration")
        self._chromatic_enable.setChecked(effect.enabled)
        self._chromatic_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._chromatic_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._chromatic_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the RGB channel offset distance.",
            default_value=0.5,
        )
        self._chromatic_intensity.setValue(effect.intensity)
        self._chromatic_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._chromatic_intensity)

        self._chromatic_direction = NoScrollComboBox()
        self._chromatic_direction.blockSignals(True)
        self._chromatic_direction.addItem("Radial", "radial")
        self._chromatic_direction.addItem("Linear", "linear")
        idx = self._chromatic_direction.findData(effect.direction)
        if idx >= 0:
            self._chromatic_direction.setCurrentIndex(idx)
        self._chromatic_direction.blockSignals(False)
        self._chromatic_direction.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Direction:", self._chromatic_direction)

        self._chromatic_angle = DragSpinBox(
            minimum=0.0,
            maximum=360.0,
            step=1.0,
            decimals=1,
            description="Angle for linear chromatic aberration direction.",
            default_value=0.0,
        )
        self._chromatic_angle.setValue(effect.angle)
        self._chromatic_angle.valueChanged.connect(self._on_effects_changed)
        self._chromatic_angle_label = QLabel("Angle:")
        sub_layout.addRow(self._chromatic_angle_label, self._chromatic_angle)

        # Show angle only for linear direction
        is_linear = effect.direction == "linear"
        self._chromatic_angle_label.setVisible(is_linear)
        self._chromatic_angle.setVisible(is_linear)

        def _toggle_angle_visibility(_idx: int) -> None:
            is_lin = self._chromatic_direction.currentData() == "linear"
            self._chromatic_angle_label.setVisible(is_lin)
            self._chromatic_angle.setVisible(is_lin)

        self._chromatic_direction.currentIndexChanged.connect(_toggle_angle_visibility)

        (
            self._chromatic_audio_cb,
            self._chromatic_audio_source,
            self._chromatic_audio_sensitivity,
            self._chromatic_audio_source_label,
            self._chromatic_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._chromatic_sub = sub
        sub.setVisible(effect.enabled)
        self._chromatic_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_glitch(self, layout: QVBoxLayout, effect: GlitchEffect) -> None:
        """Build glitch controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._glitch_enable = QCheckBox("Glitch")
        self._glitch_enable.setChecked(effect.enabled)
        self._glitch_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._glitch_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._glitch_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the severity of glitch artifacts.",
            default_value=0.5,
        )
        self._glitch_intensity.setValue(effect.intensity)
        self._glitch_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._glitch_intensity)

        self._glitch_type = NoScrollComboBox()
        self._glitch_type.blockSignals(True)
        for type_name, type_val in [
            ("Scanline", "scanline"),
            ("Block", "block"),
            ("Digital", "digital"),
        ]:
            self._glitch_type.addItem(type_name, type_val)
        idx = self._glitch_type.findData(effect.type)
        if idx >= 0:
            self._glitch_type.setCurrentIndex(idx)
        self._glitch_type.blockSignals(False)
        self._glitch_type.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Type:", self._glitch_type)

        (
            self._glitch_audio_cb,
            self._glitch_audio_source,
            self._glitch_audio_sensitivity,
            self._glitch_audio_source_label,
            self._glitch_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._glitch_sub = sub
        sub.setVisible(effect.enabled)
        self._glitch_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_film_grain(self, layout: QVBoxLayout, effect: FilmGrainEffect) -> None:
        """Build film grain controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._grain_enable = QCheckBox("Film Grain")
        self._grain_enable.setChecked(effect.enabled)
        self._grain_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._grain_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._grain_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the visibility of the film grain overlay.",
            default_value=0.5,
        )
        self._grain_intensity.setValue(effect.intensity)
        self._grain_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._grain_intensity)

        (
            self._grain_audio_cb,
            self._grain_audio_source,
            self._grain_audio_sensitivity,
            self._grain_audio_source_label,
            self._grain_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._grain_sub = sub
        sub.setVisible(effect.enabled)
        self._grain_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_bloom(self, layout: QVBoxLayout, effect: BloomEffect) -> None:
        """Build bloom/glow controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._bloom_enable = QCheckBox("Bloom")
        self._bloom_enable.setChecked(effect.enabled)
        self._bloom_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._bloom_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._bloom_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the brightness and spread of the glow.",
            default_value=0.5,
        )
        self._bloom_intensity.setValue(effect.intensity)
        self._bloom_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._bloom_intensity)

        self._bloom_threshold = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description=(
                "Luminance threshold for bloom extraction.\n"
                "Lower values cause more of the image to glow."
            ),
            default_value=0.6,
        )
        self._bloom_threshold.setValue(effect.threshold)
        self._bloom_threshold.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Threshold:", self._bloom_threshold)

        (
            self._bloom_audio_cb,
            self._bloom_audio_source,
            self._bloom_audio_sensitivity,
            self._bloom_audio_source_label,
            self._bloom_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._bloom_sub = sub
        sub.setVisible(effect.enabled)
        self._bloom_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_scanlines(self, layout: QVBoxLayout, effect: ScanlinesEffect) -> None:
        """Build CRT scanlines controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._scanline_enable = QCheckBox("Scanlines")
        self._scanline_enable.setChecked(effect.enabled)
        self._scanline_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._scanline_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._scanline_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the darkness of the scanline gaps.",
            default_value=0.5,
        )
        self._scanline_intensity.setValue(effect.intensity)
        self._scanline_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._scanline_intensity)

        self._scanline_density = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description=(
                "Controls how many scanlines are visible.\n"
                "Lower values = fewer, thicker lines.\n"
                "Higher values = denser, finer lines."
            ),
            default_value=0.5,
        )
        self._scanline_density.setValue(effect.density)
        self._scanline_density.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Density:", self._scanline_density)

        (
            self._scanline_audio_cb,
            self._scanline_audio_source,
            self._scanline_audio_sensitivity,
            self._scanline_audio_source_label,
            self._scanline_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._scanline_sub = sub
        sub.setVisible(effect.enabled)
        self._scanline_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_color_shift(self, layout: QVBoxLayout, effect: ColorShiftEffect) -> None:
        """Build global color shift (hue rotation) controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._color_shift_enable = QCheckBox("Color Shift")
        self._color_shift_enable.setChecked(effect.enabled)
        self._color_shift_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._color_shift_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._color_shift_intensity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description=(
                "Controls the amount of hue rotation applied\n"
                "to the entire composited frame.\n"
                "0 = no shift, 0.5 = 180 degrees, 1.0 = full cycle."
            ),
            default_value=0.5,
        )
        self._color_shift_intensity.setValue(effect.intensity)
        self._color_shift_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._color_shift_intensity)

        (
            self._color_shift_audio_cb,
            self._color_shift_audio_source,
            self._color_shift_audio_sensitivity,
            self._color_shift_audio_source_label,
            self._color_shift_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout,
            effect.audio,
            self._on_effects_changed,
        )

        self._color_shift_sub = sub
        sub.setVisible(effect.enabled)
        self._color_shift_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    # -- Audio reactive controls (same pattern as background_section.py) --

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
            btn = QPushButton(default_label or "Reset")
            btn.setFixedWidth(40)
            btn.setObjectName("ColorControlBtn")
            btn.clicked.connect(default_callback)
            row.addWidget(btn)
        if description:
            row.addWidget(make_help_button(description))
        return container

    def _build_audio_reactive_controls(
        self,
        form: QFormLayout,
        audio: AudioReactiveConfig,
        on_changed: Callable[[], None],
    ) -> tuple[QCheckBox, NoScrollComboBox, DragSpinBox, QLabel, QWidget]:
        """Build audio-reactive controls: checkbox, source combo, sensitivity."""
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

    # -- Signal handlers --

    def _on_effects_changed(self) -> None:
        """Collect all effect widget values into the preset and emit signal."""
        if self._preset is None or self._rebuilding:
            return

        self._preset.global_effects.apply_stage = (
            self._stage_combo.currentData() or "before_overlays"
        )

        # Vignette
        self._preset.global_effects.vignette = VignetteEffect(
            enabled=self._vignette_enable.isChecked(),
            intensity=self._vignette_intensity.value(),
            shape=self._vignette_shape.currentData() or "circular",
            audio=AudioReactiveConfig(
                enabled=self._vignette_audio_cb.isChecked(),
                source=self._vignette_audio_source.currentData() or "amplitude",
                sensitivity=self._vignette_audio_sensitivity.value(),
            ),
        )

        # Chromatic aberration
        self._preset.global_effects.chromatic_aberration = ChromaticAberrationEffect(
            enabled=self._chromatic_enable.isChecked(),
            intensity=self._chromatic_intensity.value(),
            direction=self._chromatic_direction.currentData() or "radial",
            angle=self._chromatic_angle.value(),
            audio=AudioReactiveConfig(
                enabled=self._chromatic_audio_cb.isChecked(),
                source=self._chromatic_audio_source.currentData() or "amplitude",
                sensitivity=self._chromatic_audio_sensitivity.value(),
            ),
        )

        # Glitch
        self._preset.global_effects.glitch = GlitchEffect(
            enabled=self._glitch_enable.isChecked(),
            intensity=self._glitch_intensity.value(),
            type=self._glitch_type.currentData() or "scanline",
            audio=AudioReactiveConfig(
                enabled=self._glitch_audio_cb.isChecked(),
                source=self._glitch_audio_source.currentData() or "amplitude",
                sensitivity=self._glitch_audio_sensitivity.value(),
            ),
        )

        # Film grain
        self._preset.global_effects.film_grain = FilmGrainEffect(
            enabled=self._grain_enable.isChecked(),
            intensity=self._grain_intensity.value(),
            audio=AudioReactiveConfig(
                enabled=self._grain_audio_cb.isChecked(),
                source=self._grain_audio_source.currentData() or "amplitude",
                sensitivity=self._grain_audio_sensitivity.value(),
            ),
        )

        # Bloom
        self._preset.global_effects.bloom = BloomEffect(
            enabled=self._bloom_enable.isChecked(),
            intensity=self._bloom_intensity.value(),
            threshold=self._bloom_threshold.value(),
            audio=AudioReactiveConfig(
                enabled=self._bloom_audio_cb.isChecked(),
                source=self._bloom_audio_source.currentData() or "amplitude",
                sensitivity=self._bloom_audio_sensitivity.value(),
            ),
        )

        # Scanlines
        self._preset.global_effects.scanlines = ScanlinesEffect(
            enabled=self._scanline_enable.isChecked(),
            intensity=self._scanline_intensity.value(),
            density=self._scanline_density.value(),
            audio=AudioReactiveConfig(
                enabled=self._scanline_audio_cb.isChecked(),
                source=self._scanline_audio_source.currentData() or "amplitude",
                sensitivity=self._scanline_audio_sensitivity.value(),
            ),
        )

        # Color shift
        self._preset.global_effects.color_shift = ColorShiftEffect(
            enabled=self._color_shift_enable.isChecked(),
            intensity=self._color_shift_intensity.value(),
            audio=AudioReactiveConfig(
                enabled=self._color_shift_audio_cb.isChecked(),
                source=self._color_shift_audio_source.currentData() or "amplitude",
                sensitivity=self._color_shift_audio_sensitivity.value(),
            ),
        )

        self.effects_changed.emit()

    def update_values(self, preset: Preset) -> None:
        """Sync widget values without rebuilding."""
        self._preset = preset
        self._rebuilding = True
        effects = preset.global_effects

        self._stage_combo.blockSignals(True)
        idx = self._stage_combo.findData(effects.apply_stage)
        if idx >= 0:
            self._stage_combo.setCurrentIndex(idx)
        self._stage_combo.blockSignals(False)

        # Vignette
        self._sync_effect_widgets(
            effects.vignette,
            self._vignette_enable,
            self._vignette_intensity,
            self._vignette_audio_cb,
            self._vignette_audio_source,
            self._vignette_audio_sensitivity,
            sub_widget=self._vignette_sub,
            audio_source_label=self._vignette_audio_source_label,
            audio_sens_wrapper=self._vignette_audio_sens_wrapper,
        )
        self._vignette_shape.blockSignals(True)
        idx = self._vignette_shape.findData(effects.vignette.shape)
        if idx >= 0:
            self._vignette_shape.setCurrentIndex(idx)
        self._vignette_shape.blockSignals(False)

        # Chromatic aberration
        self._sync_effect_widgets(
            effects.chromatic_aberration,
            self._chromatic_enable,
            self._chromatic_intensity,
            self._chromatic_audio_cb,
            self._chromatic_audio_source,
            self._chromatic_audio_sensitivity,
            sub_widget=self._chromatic_sub,
            audio_source_label=self._chromatic_audio_source_label,
            audio_sens_wrapper=self._chromatic_audio_sens_wrapper,
        )
        self._chromatic_direction.blockSignals(True)
        idx = self._chromatic_direction.findData(effects.chromatic_aberration.direction)
        if idx >= 0:
            self._chromatic_direction.setCurrentIndex(idx)
        self._chromatic_direction.blockSignals(False)
        self._chromatic_angle.blockSignals(True)
        self._chromatic_angle.setValue(effects.chromatic_aberration.angle)
        self._chromatic_angle.blockSignals(False)
        # Manually sync angle visibility since blockSignals suppresses currentIndexChanged
        is_linear = effects.chromatic_aberration.direction == "linear"
        self._chromatic_angle_label.setVisible(is_linear)
        self._chromatic_angle.setVisible(is_linear)

        # Glitch
        self._sync_effect_widgets(
            effects.glitch,
            self._glitch_enable,
            self._glitch_intensity,
            self._glitch_audio_cb,
            self._glitch_audio_source,
            self._glitch_audio_sensitivity,
            sub_widget=self._glitch_sub,
            audio_source_label=self._glitch_audio_source_label,
            audio_sens_wrapper=self._glitch_audio_sens_wrapper,
        )
        self._glitch_type.blockSignals(True)
        idx = self._glitch_type.findData(effects.glitch.type)
        if idx >= 0:
            self._glitch_type.setCurrentIndex(idx)
        self._glitch_type.blockSignals(False)

        # Film grain
        self._sync_effect_widgets(
            effects.film_grain,
            self._grain_enable,
            self._grain_intensity,
            self._grain_audio_cb,
            self._grain_audio_source,
            self._grain_audio_sensitivity,
            sub_widget=self._grain_sub,
            audio_source_label=self._grain_audio_source_label,
            audio_sens_wrapper=self._grain_audio_sens_wrapper,
        )

        # Bloom
        self._sync_effect_widgets(
            effects.bloom,
            self._bloom_enable,
            self._bloom_intensity,
            self._bloom_audio_cb,
            self._bloom_audio_source,
            self._bloom_audio_sensitivity,
            sub_widget=self._bloom_sub,
            audio_source_label=self._bloom_audio_source_label,
            audio_sens_wrapper=self._bloom_audio_sens_wrapper,
        )
        self._bloom_threshold.blockSignals(True)
        self._bloom_threshold.setValue(effects.bloom.threshold)
        self._bloom_threshold.blockSignals(False)

        # Scanlines
        self._sync_effect_widgets(
            effects.scanlines,
            self._scanline_enable,
            self._scanline_intensity,
            self._scanline_audio_cb,
            self._scanline_audio_source,
            self._scanline_audio_sensitivity,
            sub_widget=self._scanline_sub,
            audio_source_label=self._scanline_audio_source_label,
            audio_sens_wrapper=self._scanline_audio_sens_wrapper,
        )
        self._scanline_density.blockSignals(True)
        self._scanline_density.setValue(effects.scanlines.density)
        self._scanline_density.blockSignals(False)

        # Color shift
        self._sync_effect_widgets(
            effects.color_shift,
            self._color_shift_enable,
            self._color_shift_intensity,
            self._color_shift_audio_cb,
            self._color_shift_audio_source,
            self._color_shift_audio_sensitivity,
            sub_widget=self._color_shift_sub,
            audio_source_label=self._color_shift_audio_source_label,
            audio_sens_wrapper=self._color_shift_audio_sens_wrapper,
        )

        self._rebuilding = False

    def apply(self, preset: Preset) -> None:
        """Apply preset -- always in-place since structure is static."""
        if not self._built:
            self.build(preset)
        else:
            self.update_values(preset)

    def _sync_effect_widgets(
        self,
        effect: (
            VignetteEffect
            | ChromaticAberrationEffect
            | GlitchEffect
            | FilmGrainEffect
            | BloomEffect
            | ScanlinesEffect
            | ColorShiftEffect
        ),
        enable_cb: QCheckBox,
        intensity_spin: DragSpinBox,
        audio_cb: QCheckBox,
        audio_source: NoScrollComboBox,
        audio_sensitivity: DragSpinBox,
        sub_widget: QWidget | None = None,
        audio_source_label: QWidget | None = None,
        audio_sens_wrapper: QWidget | None = None,
    ) -> None:
        """Sync common effect widgets with blockSignals."""
        enable_cb.blockSignals(True)
        enable_cb.setChecked(effect.enabled)
        enable_cb.blockSignals(False)
        # Manually update sub-widget visibility since blockSignals suppresses toggled
        if sub_widget is not None:
            sub_widget.setVisible(effect.enabled)
        intensity_spin.blockSignals(True)
        intensity_spin.setValue(effect.intensity)
        intensity_spin.blockSignals(False)
        audio_cb.blockSignals(True)
        audio_cb.setChecked(effect.audio.enabled)
        audio_cb.blockSignals(False)
        # Manually update audio controls visibility
        if audio_source_label is not None:
            audio_source_label.setVisible(effect.audio.enabled)
        audio_source.blockSignals(True)
        audio_source.setVisible(effect.audio.enabled)
        idx = audio_source.findData(effect.audio.source)
        if idx >= 0:
            audio_source.setCurrentIndex(idx)
        audio_source.blockSignals(False)
        audio_sensitivity.blockSignals(True)
        audio_sensitivity.setValue(effect.audio.sensitivity)
        audio_sensitivity.blockSignals(False)
        if audio_sens_wrapper is not None:
            audio_sens_wrapper.setVisible(effect.audio.enabled)

"""Format, codec, quality, audio, and GIF settings section for the project settings panel."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from wavern.core.codecs import (
    AUDIO_BITRATE_OPTIONS,
    ENCODER_SPEEDS,
    get_codec_family,
    get_codecs_for_container,
    get_default_codec,
    get_quality_settings,
)
from wavern.gui.constants import PRORES_PROFILES, QUALITY_PRESET_DISPLAY
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox


class QualitySection(QWidget):
    """Format, codec, quality presets, audio bitrate, and GIF options."""

    quality_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rebuilding = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self._form = form

        # --- Format ---
        separator_fmt = QLabel("Format")
        separator_fmt.setObjectName("SectionSeparator")
        form.addRow(separator_fmt)

        fmt_row = QHBoxLayout()
        self._format_combo = NoScrollComboBox()
        self._format_combo.addItems(["mp4", "webm", "mov", "gif"])
        fmt_row.addWidget(self._format_combo, stretch=1)
        fmt_row.addWidget(make_help_button(
            "MP4 (H.264/H.265): widely compatible, smaller files, no transparency.\n"
            "WebM (VP9/AV1): supports transparency, good for overlays.\n"
            "MOV (ProRes): professional editing codec, supports transparency.\n"
            "GIF: animated image, no audio, limited colors."
        ))
        form.addRow("Format:", fmt_row)

        # Hardware Acceleration
        hw_row = QHBoxLayout()
        self._hw_accel_combo = NoScrollComboBox()
        self._hw_accel_combo.addItem("Auto (Recommended)", "auto")
        self._hw_accel_combo.addItem("Off (Software Only)", "off")
        hw_row.addWidget(self._hw_accel_combo, stretch=1)
        hw_row.addWidget(make_help_button(
            "Auto: uses GPU encoding (NVENC, VAAPI, QSV) if available.\n"
            "Off: forces CPU software encoding (slower, maximum compatibility)."
        ))
        form.addRow("HW Accel:", hw_row)
        self._hw_accel_label = form.labelForField(hw_row)

        # Codec
        codec_row = QHBoxLayout()
        self._codec_combo = NoScrollComboBox()
        self._populate_codec_combo("mp4")
        codec_row.addWidget(self._codec_combo, stretch=1)
        codec_row.addWidget(make_help_button(
            "Video codec used to encode the output.\n"
            "Each format supports different codecs with varying quality,\n"
            "speed, and compatibility trade-offs."
        ))
        form.addRow("Codec:", codec_row)
        self._codec_label = form.labelForField(codec_row)

        # --- Quality ---
        separator_q = QLabel("Quality")
        separator_q.setObjectName("SectionSeparator")
        form.addRow(separator_q)

        # Quality preset
        qp_row = QHBoxLayout()
        self._quality_combo = NoScrollComboBox()
        for value, display in QUALITY_PRESET_DISPLAY:
            self._quality_combo.addItem(display, value)
        self._quality_combo.setCurrentIndex(2)  # "High"
        qp_row.addWidget(self._quality_combo, stretch=1)
        qp_row.addWidget(make_help_button(
            "Quality preset auto-configures CRF and encoder speed.\n"
            "Highest = best quality, slowest encode, largest file.\n"
            "Lowest = worst quality, fastest encode, smallest file.\n"
            "Custom = manually set CRF and encoder speed."
        ))
        form.addRow("Preset:", qp_row)

        # CRF
        self._crf_spin = DragSpinBox(
            minimum=0, maximum=51, step=1, decimals=0, default_value=18,
            description=(
                "CRF (Constant Rate Factor) controls video quality.\n"
                "Lower = better quality, larger file.\n"
                "0 = lossless, 18 = visually lossless, 23 = default, "
                "28+ = noticeable compression."
            ),
        )
        self._crf_spin.setValue(18)
        form.addRow("CRF:", self._crf_spin)
        self._crf_label = form.labelForField(self._crf_spin)

        # Encoder speed
        speed_row = QHBoxLayout()
        self._speed_combo = NoScrollComboBox()
        self._populate_speed_combo("libx264")
        speed_row.addWidget(self._speed_combo, stretch=1)
        speed_row.addWidget(make_help_button(
            "Encoder speed trades encoding time for compression efficiency.\n"
            "Slower = better quality at same file size, but takes longer."
        ))
        form.addRow("Encoder Speed:", speed_row)
        self._speed_label = form.labelForField(speed_row)

        # ProRes profile
        prores_row = QHBoxLayout()
        self._prores_combo = NoScrollComboBox()
        for profile_id, name in PRORES_PROFILES:
            self._prores_combo.addItem(name, profile_id)
        self._prores_combo.setCurrentIndex(3)  # HQ
        prores_row.addWidget(self._prores_combo, stretch=1)
        prores_row.addWidget(make_help_button(
            "ProRes profile determines quality and data rate.\n"
            "Proxy = smallest, 4444XQ = highest quality with alpha."
        ))
        form.addRow("ProRes Profile:", prores_row)
        self._prores_label = form.labelForField(prores_row)

        # Fill detail widgets from the default "High" preset
        self._sync_quality_details_from_preset()

        # --- Audio ---
        self._audio_separator = QLabel("Audio")
        self._audio_separator.setObjectName("SectionSeparator")
        form.addRow(self._audio_separator)

        abr_row = QHBoxLayout()
        self._audio_bitrate_combo = NoScrollComboBox()
        self._audio_bitrate_combo.addItems(AUDIO_BITRATE_OPTIONS)
        self._audio_bitrate_combo.setCurrentText("192k")
        abr_row.addWidget(self._audio_bitrate_combo, stretch=1)
        abr_row.addWidget(make_help_button(
            "Audio bitrate controls audio quality.\n"
            "128k = acceptable, 192k = good, 256k = high, 320k = best."
        ))
        form.addRow("Audio Bitrate:", abr_row)
        self._audio_bitrate_label = form.labelForField(abr_row)

        # Source audio bitrate info label
        self._source_bitrate_label = QLabel("Source: —")
        self._source_bitrate_label.setObjectName("SourceBitrateLabel")
        self._source_bitrate_label.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", self._source_bitrate_label)

        # --- GIF Settings ---
        self._gif_separator = QLabel("GIF Settings")
        self._gif_separator.setObjectName("SectionSeparator")
        form.addRow(self._gif_separator)

        self._gif_colors_spin = DragSpinBox(
            minimum=64, maximum=256, step=1, decimals=0, default_value=256,
            description=(
                "Maximum number of colors in the GIF palette.\n"
                "More colors = better quality, larger file."
            ),
        )
        self._gif_colors_spin.setValue(256)
        form.addRow("Max Colors:", self._gif_colors_spin)
        self._gif_colors_label = form.labelForField(self._gif_colors_spin)

        dither_row = QHBoxLayout()
        self._gif_dither_check = QCheckBox("Enabled")
        self._gif_dither_check.setChecked(True)
        dither_row.addWidget(self._gif_dither_check)
        dither_row.addWidget(make_help_button(
            "Dithering simulates colors not in the palette by mixing nearby colors.\n"
            "Reduces banding but can add noise."
        ))
        dither_row.addStretch()
        form.addRow("Dithering:", dither_row)
        self._gif_dither_label = form.labelForField(dither_row)

        self._gif_loop_spin = DragSpinBox(
            minimum=0, maximum=9999, step=1, decimals=0, default_value=0,
            description="Number of times the GIF loops. 0 = infinite loop.",
        )
        self._gif_loop_spin.setValue(0)
        form.addRow("Loop Count:", self._gif_loop_spin)
        self._gif_loop_label = form.labelForField(self._gif_loop_spin)

        self._gif_scale_spin = DragSpinBox(
            minimum=0.25, maximum=1.0, step=0.05, decimals=2, default_value=1.0,
            description=(
                "Scale factor for GIF output.\n"
                "Lower = smaller dimensions, smaller file."
            ),
        )
        self._gif_scale_spin.setValue(1.0)
        form.addRow("Scale Factor:", self._gif_scale_spin)
        self._gif_scale_label = form.labelForField(self._gif_scale_spin)

        layout.addLayout(form)
        self._connect_signals()
        self._update_visibility()

    def _connect_signals(self) -> None:
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        self._hw_accel_combo.currentIndexChanged.connect(self._on_setting_changed)
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        self._quality_combo.currentIndexChanged.connect(
            self._on_quality_preset_changed,
        )
        self._crf_spin.valueChanged.connect(self._on_quality_detail_changed)
        self._speed_combo.currentIndexChanged.connect(
            self._on_quality_detail_changed,
        )
        self._prores_combo.currentIndexChanged.connect(
            self._on_quality_detail_changed,
        )
        self._audio_bitrate_combo.currentIndexChanged.connect(
            self._on_setting_changed,
        )
        self._gif_colors_spin.valueChanged.connect(self._on_setting_changed)
        self._gif_dither_check.stateChanged.connect(self._on_setting_changed)
        self._gif_loop_spin.valueChanged.connect(self._on_setting_changed)
        self._gif_scale_spin.valueChanged.connect(self._on_setting_changed)

    def collect(self) -> dict:
        """Return current format/quality/audio/GIF settings as a dict.

        Returns:
            Dict with container, video_codec, quality_preset, crf,
            encoder_speed, prores_profile, audio_bitrate, hw_accel,
            and gif_* keys.
        """
        codec_id = self._codec_combo.currentData() or ""
        return {
            "container": self._format_combo.currentText(),
            "video_codec": codec_id,
            "quality_preset": self._quality_combo.currentData() or "high",
            "crf": int(self._crf_spin.value()),
            "encoder_speed": self._speed_combo.currentData() or "medium",
            "prores_profile": (
                self._prores_combo.currentData()
                if self._prores_combo.currentData() is not None
                else 3
            ),
            "audio_bitrate": self._audio_bitrate_combo.currentText(),
            "hw_accel": self._hw_accel_combo.currentData() or "auto",
            "gif_max_colors": int(self._gif_colors_spin.value()),
            "gif_dither": self._gif_dither_check.isChecked(),
            "gif_loop": int(self._gif_loop_spin.value()),
            "gif_scale": float(self._gif_scale_spin.value()),
        }

    def reset(self, defaults: object) -> None:
        """Reset all widgets to default values.

        Args:
            defaults: A ProjectSettings instance with default values.
        """
        self._rebuilding = True
        self._format_combo.blockSignals(True)
        self._hw_accel_combo.blockSignals(True)
        self._codec_combo.blockSignals(True)
        self._quality_combo.blockSignals(True)
        self._crf_spin.blockSignals(True)
        self._speed_combo.blockSignals(True)
        self._prores_combo.blockSignals(True)
        self._audio_bitrate_combo.blockSignals(True)
        self._gif_colors_spin.blockSignals(True)
        self._gif_dither_check.blockSignals(True)
        self._gif_loop_spin.blockSignals(True)
        self._gif_scale_spin.blockSignals(True)

        idx = self._format_combo.findText(defaults.container)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        self._hw_accel_combo.setCurrentIndex(0)  # Auto
        self._populate_codec_combo(defaults.container)
        self._quality_combo.setCurrentIndex(2)  # High
        self._crf_spin.setValue(defaults.crf)
        self._populate_speed_combo(get_default_codec(defaults.container))
        idx = self._prores_combo.findData(defaults.prores_profile)
        if idx >= 0:
            self._prores_combo.setCurrentIndex(idx)
        self._audio_bitrate_combo.setCurrentText(defaults.audio_bitrate)
        self._gif_colors_spin.setValue(defaults.gif_max_colors)
        self._gif_dither_check.setChecked(defaults.gif_dither)
        self._gif_loop_spin.setValue(defaults.gif_loop)
        self._gif_scale_spin.setValue(defaults.gif_scale)

        self._format_combo.blockSignals(False)
        self._hw_accel_combo.blockSignals(False)
        self._codec_combo.blockSignals(False)
        self._quality_combo.blockSignals(False)
        self._crf_spin.blockSignals(False)
        self._speed_combo.blockSignals(False)
        self._prores_combo.blockSignals(False)
        self._audio_bitrate_combo.blockSignals(False)
        self._gif_colors_spin.blockSignals(False)
        self._gif_dither_check.blockSignals(False)
        self._gif_loop_spin.blockSignals(False)
        self._gif_scale_spin.blockSignals(False)
        self._rebuilding = False

        self._sync_quality_details_from_preset()
        self._update_visibility()

    # --- Public API ---

    def set_alpha_mode(self, enabled: bool) -> None:
        """Enable/disable alpha-only format restrictions.

        When enabled, disables format options that don't support transparency
        (mp4, gif) and switches to webm if the current format is incompatible.

        Args:
            enabled: True when background is transparent ("none").
        """
        alpha_containers = {"webm", "mov"}

        for i in range(self._format_combo.count()):
            fmt = self._format_combo.itemText(i)
            item_model = self._format_combo.model()
            item = item_model.item(i)
            if enabled and fmt not in alpha_containers:
                item.setEnabled(False)
            else:
                item.setEnabled(True)

        if enabled and self._format_combo.currentText() not in alpha_containers:
            self._format_combo.setCurrentText("webm")

    def set_format(self, fmt: str) -> None:
        """Programmatically set the container format.

        Args:
            fmt: Container format string (e.g. "mp4", "webm").
        """
        self._format_combo.blockSignals(True)
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        self._format_combo.blockSignals(False)
        self._populate_codec_combo(fmt)
        self._populate_speed_combo(self._codec_combo.currentData() or "")
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self.quality_changed.emit()

    def set_audio_metadata(self, bitrate: int | None) -> None:
        """Update the source audio bitrate info label.

        Args:
            bitrate: Source audio bitrate in kbps, or None if unknown.
        """
        if bitrate is not None:
            self._source_bitrate_label.setText(f"Source: {bitrate} kbps")
        else:
            self._source_bitrate_label.setText("Source: —")

    # --- Internal helpers ---

    def _populate_codec_combo(self, container: str) -> None:
        """Populate codec combo for the given container."""
        self._codec_combo.blockSignals(True)
        self._codec_combo.clear()
        codecs = get_codecs_for_container(container)
        for desc in codecs:
            self._codec_combo.addItem(desc.display_name, desc.codec_id)
        self._codec_combo.blockSignals(False)

    def _populate_speed_combo(self, codec_id: str) -> None:
        """Populate encoder speed combo for the given codec."""
        self._speed_combo.blockSignals(True)
        self._speed_combo.clear()
        family = get_codec_family(codec_id)
        speeds = ENCODER_SPEEDS.get(family, [])
        for speed in speeds:
            self._speed_combo.addItem(speed, speed)
        if speeds:
            default = "medium" if family in ("x264", "x265") else "4"
            idx = self._speed_combo.findData(default)
            if idx >= 0:
                self._speed_combo.setCurrentIndex(idx)
        self._speed_combo.blockSignals(False)

    def _sync_quality_details_from_preset(self) -> None:
        """Fill CRF/speed/ProRes widgets from the selected quality preset."""
        preset_name = self._quality_combo.currentData()
        if not preset_name or preset_name == "custom":
            return

        codec_id = self._codec_combo.currentData() or ""
        if not codec_id:
            return

        try:
            settings = get_quality_settings(preset_name, codec_id)
        except ValueError:
            return

        self._rebuilding = True

        if "crf" in settings:
            self._crf_spin.blockSignals(True)
            self._crf_spin.setValue(settings["crf"])
            self._crf_spin.blockSignals(False)

        if "encoder_speed" in settings:
            self._speed_combo.blockSignals(True)
            idx = self._speed_combo.findData(settings["encoder_speed"])
            if idx >= 0:
                self._speed_combo.setCurrentIndex(idx)
            self._speed_combo.blockSignals(False)

        if "prores_profile" in settings:
            self._prores_combo.blockSignals(True)
            idx = self._prores_combo.findData(settings["prores_profile"])
            if idx >= 0:
                self._prores_combo.setCurrentIndex(idx)
            self._prores_combo.blockSignals(False)

        self._rebuilding = False

    def _update_visibility(self) -> None:
        """Show/hide widgets based on current container and codec."""
        container = self._format_combo.currentText()
        codec_id = self._codec_combo.currentData() or ""
        family = get_codec_family(codec_id)
        is_gif = container == "gif"
        is_prores = family == "prores"
        has_crf = not is_prores and not is_gif
        has_speed = family in ("x264", "x265", "vp9", "av1")

        # HW Accel: hide for gif
        self._set_layout_row_visible(self._hw_accel_combo, not is_gif)
        if self._hw_accel_label:
            self._hw_accel_label.setVisible(not is_gif)

        # Codec row: hide for gif
        codec_visible = not is_gif
        self._codec_combo.setVisible(codec_visible)
        if self._codec_label:
            self._codec_label.setVisible(codec_visible)

        # Quality preset: hide for GIF
        self._quality_combo.setVisible(not is_gif)
        self._set_layout_row_visible(self._quality_combo, not is_gif)

        # CRF
        self._crf_spin.setVisible(has_crf)
        if self._crf_label:
            self._crf_label.setVisible(has_crf)

        # Encoder speed
        self._set_layout_row_visible(self._speed_combo, has_speed)
        if self._speed_label:
            self._speed_label.setVisible(has_speed)

        # ProRes profile
        self._set_layout_row_visible(self._prores_combo, is_prores)
        if self._prores_label:
            self._prores_label.setVisible(is_prores)

        # Audio section: hidden for GIF
        audio_visible = not is_gif
        self._audio_separator.setVisible(audio_visible)
        self._set_layout_row_visible(self._audio_bitrate_combo, audio_visible)
        if self._audio_bitrate_label:
            self._audio_bitrate_label.setVisible(audio_visible)
        self._source_bitrate_label.setVisible(audio_visible)

        # GIF section: visible only for GIF
        self._gif_separator.setVisible(is_gif)
        self._gif_colors_spin.setVisible(is_gif)
        self._set_layout_row_visible(self._gif_dither_check, is_gif)
        self._gif_loop_spin.setVisible(is_gif)
        self._gif_scale_spin.setVisible(is_gif)
        if self._gif_colors_label:
            self._gif_colors_label.setVisible(is_gif)
        if self._gif_dither_label:
            self._gif_dither_label.setVisible(is_gif)
        if self._gif_loop_label:
            self._gif_loop_label.setVisible(is_gif)
        if self._gif_scale_label:
            self._gif_scale_label.setVisible(is_gif)

    def _set_layout_row_visible(
        self, target_widget: QWidget, visible: bool,
    ) -> None:
        """Show/hide all widgets in the same form layout row as target_widget."""
        for i in range(self._form.rowCount()):
            item = self._form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if item and item.layout():
                for j in range(item.layout().count()):
                    w = item.layout().itemAt(j).widget()
                    if w is target_widget:
                        for k in range(item.layout().count()):
                            widget = item.layout().itemAt(k).widget()
                            if widget:
                                widget.setVisible(visible)
                        return

    # --- Callbacks ---

    def _on_format_changed(self) -> None:
        if self._rebuilding:
            return
        container = self._format_combo.currentText()
        self._populate_codec_combo(container)
        self._populate_speed_combo(self._codec_combo.currentData() or "")
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self.quality_changed.emit()

    def _on_codec_changed(self) -> None:
        if self._rebuilding:
            return
        codec_id = self._codec_combo.currentData() or ""
        self._populate_speed_combo(codec_id)
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self.quality_changed.emit()

    def _on_quality_preset_changed(self) -> None:
        """Quality preset combo changed — fill detail widgets."""
        if self._rebuilding:
            return
        self._sync_quality_details_from_preset()
        self.quality_changed.emit()

    def _on_quality_detail_changed(self) -> None:
        """CRF, speed, or ProRes profile manually changed — switch to Custom."""
        if self._rebuilding:
            return
        self._quality_combo.blockSignals(True)
        custom_idx = self._quality_combo.findData("custom")
        if custom_idx >= 0:
            self._quality_combo.setCurrentIndex(custom_idx)
        self._quality_combo.blockSignals(False)
        self.quality_changed.emit()

    def _on_setting_changed(self) -> None:
        if self._rebuilding:
            return
        self.quality_changed.emit()

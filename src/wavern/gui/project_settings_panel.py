"""Project settings panel — resolution, FPS, format, codec, quality, output directory."""

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from wavern.core.codecs import (
    AUDIO_BITRATE_OPTIONS,
    ENCODER_SPEEDS,
    QUALITY_PRESETS,
    get_codec_family,
    get_codecs_for_container,
    get_default_codec,
    get_quality_settings,
)
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import ProjectSettings

logger = logging.getLogger(__name__)

# Aspect ratio → list of (width, height) presets
_RESOLUTION_PRESETS: dict[str, list[tuple[int, int]]] = {
    "16:9": [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)],
    "9:16": [(720, 1280), (1080, 1920), (1440, 2560)],
    "1:1": [(720, 720), (1080, 1080), (1440, 1440), (2160, 2160)],
    "4:3": [(960, 720), (1440, 1080), (1920, 1440)],
    "3:4": [(720, 960), (1080, 1440), (1440, 1920)],
    "21:9": [(2560, 1080), (3440, 1440), (5120, 2160)],
    "9:21": [(1080, 2560), (1440, 3440)],
    "2:3": [(720, 1080), (960, 1440), (1440, 2160)],
    "3:2": [(1080, 720), (1440, 960), (2160, 1440)],
}

_ASPECT_RATIOS = [
    "1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "9:21", "2:3", "3:2", "Custom"
]

_FPS_OPTIONS = [24, 25, 30, 60, 120]

_QUALITY_PRESET_DISPLAY = [
    ("highest", "Highest"),
    ("very_high", "Very High"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("lowest", "Lowest"),
    ("custom", "Custom"),
]

_PRORES_PROFILES = [
    (0, "Proxy"),
    (1, "LT"),
    (2, "Normal"),
    (3, "HQ"),
    (4, "4444"),
    (5, "4444XQ"),
]


class ProjectSettingsPanel(QWidget):
    """Panel for project-wide output settings."""

    settings_changed = Signal(object)  # emits ProjectSettings
    export_requested = Signal()  # user clicked the Export button in the panel

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = ProjectSettings()
        self._rebuilding = False
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._setup_ui()

    @property
    def settings(self) -> ProjectSettings:
        return self._settings

    def _setup_ui(self) -> None:
        form = QFormLayout(self)
        form.setContentsMargins(4, 0, 4, 0)
        self._form = form

        # --- Reset All ---
        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedWidth(90)
        reset_btn.clicked.connect(self._on_reset_all)
        form.addRow("", reset_btn)

        # --- Resolution ---
        separator_res = QLabel("Resolution")
        separator_res.setObjectName("SectionSeparator")
        form.addRow(separator_res)

        # Aspect ratio
        aspect_row = QHBoxLayout()
        self._aspect_combo = NoScrollComboBox()
        self._aspect_combo.addItems(_ASPECT_RATIOS)
        self._aspect_combo.setCurrentText("16:9")
        aspect_row.addWidget(self._aspect_combo, stretch=1)
        aspect_row.addWidget(make_help_button(
            "Aspect ratio determines the shape of the output video.\n"
            "Select 'Custom' to enter arbitrary dimensions."
        ))
        form.addRow("Aspect Ratio:", aspect_row)

        # Resolution quick-select
        quick_row = QHBoxLayout()
        self._res_combo = NoScrollComboBox()
        self._populate_resolution_combo("16:9")
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == (1920, 1080):
                self._res_combo.setCurrentIndex(i)
                break
        quick_row.addWidget(self._res_combo, stretch=1)
        quick_row.addWidget(make_help_button(
            "Resolution is the pixel dimensions of the output video.\n"
            "Higher resolution = sharper image but larger file and slower export."
        ))
        form.addRow("Preset:", quick_row)

        # Manual width x height
        dim_row = QHBoxLayout()
        self._width_spin = DragSpinBox(minimum=320, maximum=7680, step=1, decimals=0, default_value=1920)
        self._width_spin.setValue(1920)
        dim_row.addWidget(self._width_spin)
        dim_row.addWidget(QLabel("x"))
        self._height_spin = DragSpinBox(minimum=240, maximum=4320, step=1, decimals=0, default_value=1080)
        self._height_spin.setValue(1080)
        dim_row.addWidget(self._height_spin)
        form.addRow("Size:", dim_row)

        # --- Frame Rate ---
        separator_fps = QLabel("Frame Rate")
        separator_fps.setObjectName("SectionSeparator")
        form.addRow(separator_fps)

        fps_row = QHBoxLayout()
        self._fps_combo = NoScrollComboBox()
        for fps in _FPS_OPTIONS:
            self._fps_combo.addItem(str(fps), fps)
        self._fps_combo.addItem("Custom", -1)
        self._fps_combo.setCurrentIndex(3)  # 60
        fps_row.addWidget(self._fps_combo, stretch=1)
        fps_row.addWidget(make_help_button(
            "Frames per second — how many images are rendered each second.\n"
            "Higher FPS = smoother motion but larger file.\n"
            "24/25 = cinematic, 30 = standard, 60 = smooth, 120 = very smooth."
        ))
        form.addRow("FPS:", fps_row)

        self._fps_spin = DragSpinBox(minimum=1, maximum=240, step=1, decimals=0, default_value=60)
        self._fps_spin.setValue(60)
        form.addRow("Value:", self._fps_spin)

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

        # Quality preset (quick-select, like Aspect Ratio or FPS combo)
        qp_row = QHBoxLayout()
        self._quality_combo = NoScrollComboBox()
        for value, display in _QUALITY_PRESET_DISPLAY:
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

        # CRF — always visible for CRF-based codecs
        self._crf_spin = DragSpinBox(
            minimum=0, maximum=51, step=1, decimals=0, default_value=18,
            description=(
                "CRF (Constant Rate Factor) controls video quality.\n"
                "Lower = better quality, larger file.\n"
                "0 = lossless, 18 = visually lossless, 23 = default, 28+ = noticeable compression."
            ),
        )
        self._crf_spin.setValue(18)
        form.addRow("CRF:", self._crf_spin)
        self._crf_label = form.labelForField(self._crf_spin)

        # Encoder speed — always visible for codecs that have speed options
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

        # ProRes profile — always visible for ProRes codec
        prores_row = QHBoxLayout()
        self._prores_combo = NoScrollComboBox()
        for profile_id, name in _PRORES_PROFILES:
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
            description="Maximum number of colors in the GIF palette.\nMore colors = better quality, larger file.",
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
            description="Scale factor for GIF output.\nLower = smaller dimensions, smaller file.",
        )
        self._gif_scale_spin.setValue(1.0)
        form.addRow("Scale Factor:", self._gif_scale_spin)
        self._gif_scale_label = form.labelForField(self._gif_scale_spin)

        # --- Output Directory ---
        separator_out = QLabel("Output")
        separator_out.setObjectName("SectionSeparator")
        form.addRow(separator_out)

        out_row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("Default: ./video/")
        out_row.addWidget(self._output_edit, stretch=1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_output)
        out_row.addWidget(browse_btn)
        out_row.addWidget(make_help_button(
            "Default directory where exported videos are saved.\n"
            "Leave empty to use ./video/ relative to the project."
        ))
        form.addRow("Directory:", out_row)

        filename_row = QHBoxLayout()
        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText("Default: derived from audio file")
        filename_row.addWidget(self._filename_edit, stretch=1)
        filename_row.addWidget(make_help_button(
            "Output filename (without extension).\n"
            "Leave empty to use the audio file name."
        ))
        form.addRow("Filename:", filename_row)

        export_btn = QPushButton("Export")
        export_btn.setObjectName("ExportButton")
        export_btn.clicked.connect(self.export_requested)
        form.addRow(export_btn)

        self._connect_signals()
        self._update_visibility()

    def _connect_signals(self) -> None:
        self._aspect_combo.currentTextChanged.connect(self._on_aspect_changed)
        self._res_combo.currentIndexChanged.connect(self._on_res_preset_changed)
        self._width_spin.valueChanged.connect(self._on_dimension_changed)
        self._height_spin.valueChanged.connect(self._on_dimension_changed)
        self._fps_combo.currentIndexChanged.connect(self._on_fps_combo_changed)
        self._fps_spin.valueChanged.connect(self._on_fps_spin_changed)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        self._hw_accel_combo.currentIndexChanged.connect(self._on_setting_changed)
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        self._quality_combo.currentIndexChanged.connect(self._on_quality_preset_changed)
        self._crf_spin.valueChanged.connect(self._on_quality_detail_changed)
        self._speed_combo.currentIndexChanged.connect(self._on_quality_detail_changed)
        self._prores_combo.currentIndexChanged.connect(self._on_quality_detail_changed)
        self._audio_bitrate_combo.currentIndexChanged.connect(self._on_setting_changed)
        self._gif_colors_spin.valueChanged.connect(self._on_setting_changed)
        self._gif_dither_check.stateChanged.connect(self._on_setting_changed)
        self._gif_loop_spin.valueChanged.connect(self._on_setting_changed)
        self._gif_scale_spin.valueChanged.connect(self._on_setting_changed)
        self._output_edit.textChanged.connect(self._on_setting_changed)
        self._filename_edit.textChanged.connect(self._on_setting_changed)

    def _populate_resolution_combo(self, aspect: str) -> None:
        """Populate resolution combo for the given aspect ratio."""
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        presets = _RESOLUTION_PRESETS.get(aspect, [])
        for w, h in presets:
            self._res_combo.addItem(f"{w}x{h}", (w, h))
        self._res_combo.blockSignals(False)

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
        """Fill CRF/speed/ProRes widgets from the currently selected quality preset."""
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

        # HW Accel: hide for gif (no HW variants)
        self._set_layout_row_visible(self._hw_accel_combo, not is_gif)
        if self._hw_accel_label:
            self._hw_accel_label.setVisible(not is_gif)

        # Codec row: hide for gif (only one codec)
        codec_visible = not is_gif
        self._codec_combo.setVisible(codec_visible)
        if self._codec_label:
            self._codec_label.setVisible(codec_visible)

        # Quality preset: hide for GIF
        # (find quality combo row and toggle)
        self._quality_combo.setVisible(not is_gif)
        # The help button in the quality row needs to be toggled too
        self._set_layout_row_visible(self._quality_combo, not is_gif)

        # CRF: visible for CRF-based codecs (not ProRes, not GIF)
        self._crf_spin.setVisible(has_crf)
        if self._crf_label:
            self._crf_label.setVisible(has_crf)

        # Encoder speed: visible for codecs with speed options
        self._set_layout_row_visible(self._speed_combo, has_speed)
        if self._speed_label:
            self._speed_label.setVisible(has_speed)

        # ProRes profile: visible only for ProRes
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

    def _set_layout_row_visible(self, target_widget: QWidget, visible: bool) -> None:
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

    # --- Resolution callbacks ---

    def _on_aspect_changed(self, aspect: str) -> None:
        if aspect == "Custom":
            self._res_combo.setEnabled(False)
            return

        self._res_combo.setEnabled(True)
        self._populate_resolution_combo(aspect)

        if self._res_combo.count() > 0:
            current = (int(self._width_spin.value()), int(self._height_spin.value()))
            best_idx = 0
            for i in range(self._res_combo.count()):
                res = self._res_combo.itemData(i)
                if res == current:
                    best_idx = i
                    break
            self._res_combo.setCurrentIndex(best_idx)
            self._sync_spinboxes_from_combo()

    def _on_res_preset_changed(self, index: int) -> None:
        if index < 0:
            return
        self._sync_spinboxes_from_combo()

    def _sync_spinboxes_from_combo(self) -> None:
        """Update width/height spinboxes from the resolution combo selection."""
        data = self._res_combo.currentData()
        if data is None:
            return
        w, h = data
        self._rebuilding = True
        self._width_spin.setValue(w)
        self._height_spin.setValue(h)
        self._rebuilding = False
        self._update_settings()

    def _on_dimension_changed(self) -> None:
        if self._rebuilding:
            return
        self._aspect_combo.blockSignals(True)
        self._aspect_combo.setCurrentText("Custom")
        self._aspect_combo.blockSignals(False)
        self._res_combo.setEnabled(False)
        self._update_settings()

    # --- Frame Rate callbacks ---

    def _on_fps_combo_changed(self, index: int) -> None:
        fps_val = self._fps_combo.currentData()
        if fps_val != -1:
            self._rebuilding = True
            self._fps_spin.setValue(fps_val)
            self._rebuilding = False
        self._update_settings()

    def _on_fps_spin_changed(self) -> None:
        if self._rebuilding:
            return
        value = int(self._fps_spin.value())
        match_idx = -1
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == value:
                match_idx = i
                break
        self._fps_combo.blockSignals(True)
        if match_idx >= 0:
            self._fps_combo.setCurrentIndex(match_idx)
        else:
            custom_idx = self._fps_combo.findData(-1)
            if custom_idx >= 0:
                self._fps_combo.setCurrentIndex(custom_idx)
        self._fps_combo.blockSignals(False)
        self._update_settings()

    # --- Format / Codec callbacks ---

    def _on_format_changed(self) -> None:
        if self._rebuilding:
            return
        container = self._format_combo.currentText()
        self._populate_codec_combo(container)
        self._populate_speed_combo(self._codec_combo.currentData() or "")
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self._update_settings()

    def _on_codec_changed(self) -> None:
        if self._rebuilding:
            return
        codec_id = self._codec_combo.currentData() or ""
        self._populate_speed_combo(codec_id)
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self._update_settings()

    # --- Quality callbacks ---

    def _on_quality_preset_changed(self) -> None:
        """Quality preset combo changed — fill detail widgets from preset values."""
        if self._rebuilding:
            return
        self._sync_quality_details_from_preset()
        self._update_settings()

    def _on_quality_detail_changed(self) -> None:
        """CRF, speed, or ProRes profile manually changed — switch preset to Custom."""
        if self._rebuilding:
            return
        # Auto-switch to Custom (like dimension change → Custom aspect ratio)
        self._quality_combo.blockSignals(True)
        custom_idx = self._quality_combo.findData("custom")
        if custom_idx >= 0:
            self._quality_combo.setCurrentIndex(custom_idx)
        self._quality_combo.blockSignals(False)
        self._update_settings()

    # --- Other callbacks ---

    def _on_setting_changed(self) -> None:
        if self._rebuilding:
            return
        self._update_settings()

    def _on_browse_output(self) -> None:
        default_dir = str(Path(__file__).resolve().parents[3] / "video")
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory", default_dir)
        if path:
            self._output_edit.setText(path)

    # --- Public API ---

    def set_alpha_mode(self, enabled: bool) -> None:
        """Enable/disable alpha-only format restrictions.

        When enabled, disables format options that don't support transparency
        (mp4, gif) and switches to webm if the current format is incompatible.

        Args:
            enabled: True when background is transparent ("none").
        """
        self._alpha_mode = enabled
        # Alpha-capable containers
        alpha_containers = {"webm", "mov"}

        for i in range(self._format_combo.count()):
            fmt = self._format_combo.itemText(i)
            item_model = self._format_combo.model()
            item = item_model.item(i)
            if enabled and fmt not in alpha_containers:
                item.setEnabled(False)
            else:
                item.setEnabled(True)

        # If current format is not alpha-capable, switch to webm
        if enabled and self._format_combo.currentText() not in alpha_containers:
            self._format_combo.setCurrentText("webm")

    def set_format(self, fmt: str) -> None:
        """Programmatically set the container format without emitting settings_changed."""
        self._format_combo.blockSignals(True)
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        self._format_combo.blockSignals(False)
        self._populate_codec_combo(fmt)
        self._populate_speed_combo(self._codec_combo.currentData() or "")
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self._update_settings()

    def set_audio_metadata(self, bitrate: int | None) -> None:
        """Update the source audio bitrate info label.

        Args:
            bitrate: Source audio bitrate in kbps, or None if unknown.
        """
        if bitrate is not None:
            self._source_bitrate_label.setText(f"Source: {bitrate} kbps")
        else:
            self._source_bitrate_label.setText("Source: —")

    def _on_reset_all(self) -> None:
        """Reset all export settings to defaults."""
        defaults = ProjectSettings()
        self._rebuilding = True

        self._aspect_combo.blockSignals(True)
        self._res_combo.blockSignals(True)
        self._width_spin.blockSignals(True)
        self._height_spin.blockSignals(True)
        self._fps_combo.blockSignals(True)
        self._fps_spin.blockSignals(True)
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

        self._aspect_combo.setCurrentText("16:9")
        self._populate_resolution_combo("16:9")
        self._res_combo.setEnabled(True)
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == defaults.resolution:
                self._res_combo.setCurrentIndex(i)
                break
        self._width_spin.setValue(defaults.resolution[0])
        self._height_spin.setValue(defaults.resolution[1])
        self._fps_spin.setValue(defaults.fps)
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == defaults.fps:
                self._fps_combo.setCurrentIndex(i)
                break
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

        self._aspect_combo.blockSignals(False)
        self._res_combo.blockSignals(False)
        self._width_spin.blockSignals(False)
        self._height_spin.blockSignals(False)
        self._fps_combo.blockSignals(False)
        self._fps_spin.blockSignals(False)
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

        self._output_edit.setText(defaults.output_dir)
        self._filename_edit.setText(defaults.output_filename)
        self._sync_quality_details_from_preset()
        self._update_visibility()
        self._update_settings()

    def _update_settings(self) -> None:
        """Rebuild ProjectSettings from current widget state and emit signal."""
        codec_id = self._codec_combo.currentData() or ""
        self._settings = ProjectSettings(
            resolution=(int(self._width_spin.value()), int(self._height_spin.value())),
            fps=int(self._fps_spin.value()),
            container=self._format_combo.currentText(),
            crf=int(self._crf_spin.value()),
            output_dir=self._output_edit.text().strip(),
            output_filename=self._filename_edit.text().strip(),
            video_codec=codec_id,
            quality_preset=self._quality_combo.currentData() or "high",
            encoder_speed=self._speed_combo.currentData() or "medium",
            audio_bitrate=self._audio_bitrate_combo.currentText(),
            prores_profile=self._prores_combo.currentData() if self._prores_combo.currentData() is not None else 3,
            gif_max_colors=int(self._gif_colors_spin.value()),
            gif_dither=self._gif_dither_check.isChecked(),
            gif_loop=int(self._gif_loop_spin.value()),
            gif_scale=float(self._gif_scale_spin.value()),
            hw_accel=self._hw_accel_combo.currentData() or "auto",
        )
        self.settings_changed.emit(self._settings)

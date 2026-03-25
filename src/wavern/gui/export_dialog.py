"""Export settings dialog — resolution, format, codec, quality."""

import logging
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.collapsible_section import CollapsibleSection
from wavern.core.codecs import (
    AUDIO_BITRATE_OPTIONS,
    ENCODER_SPEEDS,
    get_codec_family,
    get_codecs_for_container,
    get_default_codec,
    get_quality_settings,
    supports_alpha,
)
from wavern.core.export import ExportConfig
from wavern.gui.export_worker import ExportWorker
from wavern.gui.constants import ALL_EXTENSIONS, PRORES_PROFILES, QUALITY_PRESET_DISPLAY
from wavern.presets.schema import Preset, ProjectSettings

logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """Export settings and progress dialog."""

    def __init__(
        self,
        audio_path: Path,
        preset: Preset,
        project_settings: ProjectSettings | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Render Video")
        self.setMinimumWidth(450)
        self._audio_path = audio_path
        self._preset = preset
        self._project_settings = project_settings or ProjectSettings()
        self._worker: ExportWorker | None = None
        self._rebuilding = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._form = form

        ps = self._project_settings

        # Output path
        output_layout = QHBoxLayout()
        self._output_edit = QLineEdit()
        if ps.output_dir:
            default_dir = Path(ps.output_dir)
        else:
            default_dir = Path(__file__).resolve().parents[3] / "video"
        default_dir.mkdir(exist_ok=True)
        stem = ps.output_filename or (self._audio_path.stem if self._audio_path else "output")
        ext = ps.container
        self._output_edit.setText(str(default_dir / f"{stem}.{ext}"))
        output_layout.addWidget(self._output_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        output_layout.addWidget(browse_btn)
        form.addRow("Output:", output_layout)

        # Resolution
        res_layout = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(320, 7680)
        self._width_spin.setValue(ps.resolution[0])
        res_layout.addWidget(self._width_spin)
        res_layout.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(240, 4320)
        self._height_spin.setValue(ps.resolution[1])
        res_layout.addWidget(self._height_spin)
        form.addRow("Resolution:", res_layout)

        # FPS
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(24, 144)
        self._fps_spin.setValue(ps.fps)
        form.addRow("FPS:", self._fps_spin)

        # Format
        self._format_combo = QComboBox()
        self._format_combo.addItems(["mp4", "webm", "mov", "gif"])
        self._format_combo.setCurrentText(ps.container)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        form.addRow("Format:", self._format_combo)

        # Hardware Acceleration
        self._hw_accel_combo = QComboBox()
        self._hw_accel_combo.addItem("Auto (Recommended)", "auto")
        self._hw_accel_combo.addItem("Off (Software Only)", "off")
        hw_idx = self._hw_accel_combo.findData(ps.hw_accel)
        if hw_idx >= 0:
            self._hw_accel_combo.setCurrentIndex(hw_idx)
        form.addRow("HW Accel:", self._hw_accel_combo)
        self._hw_accel_label = form.labelForField(self._hw_accel_combo)

        # Codec
        self._codec_combo = QComboBox()
        self._populate_codec_combo(self._format_combo.currentText())
        # Pre-select from project settings if applicable
        if ps.video_codec:
            idx = self._codec_combo.findData(ps.video_codec)
            if idx >= 0:
                self._codec_combo.setCurrentIndex(idx)
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        form.addRow("Codec:", self._codec_combo)
        self._codec_label = form.labelForField(self._codec_combo)

        # Quality preset (quick-select, always visible)
        self._quality_combo = QComboBox()
        for value, display in QUALITY_PRESET_DISPLAY:
            self._quality_combo.addItem(display, value)
        # Set from project settings
        for i in range(self._quality_combo.count()):
            if self._quality_combo.itemData(i) == ps.quality_preset:
                self._quality_combo.setCurrentIndex(i)
                break
        self._quality_combo.currentIndexChanged.connect(self._on_quality_preset_changed)
        form.addRow("Quality:", self._quality_combo)

        # CRF (always visible for CRF-based codecs)
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(ps.crf)
        self._crf_spin.valueChanged.connect(self._on_quality_detail_changed)
        form.addRow("CRF:", self._crf_spin)
        self._crf_label = form.labelForField(self._crf_spin)

        # Encoder speed (always visible for codecs that support it)
        self._speed_combo = QComboBox()
        self._populate_speed_combo(self._codec_combo.currentData() or "")
        self._speed_combo.currentIndexChanged.connect(self._on_quality_detail_changed)
        form.addRow("Encoder Speed:", self._speed_combo)
        self._speed_label = form.labelForField(self._speed_combo)

        # ProRes profile (always visible for ProRes)
        self._prores_combo = QComboBox()
        for profile_id, name in PRORES_PROFILES:
            self._prores_combo.addItem(name, profile_id)
        idx = self._prores_combo.findData(ps.prores_profile)
        if idx >= 0:
            self._prores_combo.setCurrentIndex(idx)
        self._prores_combo.currentIndexChanged.connect(self._on_quality_detail_changed)
        form.addRow("ProRes Profile:", self._prores_combo)
        self._prores_label = form.labelForField(self._prores_combo)

        # Audio bitrate
        self._audio_bitrate_combo = QComboBox()
        self._audio_bitrate_combo.addItems(AUDIO_BITRATE_OPTIONS)
        self._audio_bitrate_combo.setCurrentText(ps.audio_bitrate)
        form.addRow("Audio Bitrate:", self._audio_bitrate_combo)
        self._audio_bitrate_label = form.labelForField(self._audio_bitrate_combo)

        # Intro / Outro section
        self._concat_section = self._build_concat_section()
        form.addRow(self._concat_section)

        # Pre-fill intro/outro from project settings
        if ps.intro_path:
            self._intro_edit.setText(ps.intro_path)
            self._probe_and_show_clip_info(Path(ps.intro_path), self._intro_info_label)
        self._intro_keep_audio.setChecked(ps.intro_keep_audio)
        self._intro_fade_in.setValue(ps.intro_fade_in)
        self._intro_fade_out.setValue(ps.intro_fade_out)
        if ps.outro_path:
            self._outro_edit.setText(ps.outro_path)
            self._probe_and_show_clip_info(Path(ps.outro_path), self._outro_info_label)
        self._outro_keep_audio.setChecked(ps.outro_keep_audio)
        self._outro_fade_in.setValue(ps.outro_fade_in)
        self._outro_fade_out.setValue(ps.outro_fade_out)

        # GIF settings
        self._gif_colors_spin = QSpinBox()
        self._gif_colors_spin.setRange(64, 256)
        self._gif_colors_spin.setValue(ps.gif_max_colors)
        form.addRow("GIF Colors:", self._gif_colors_spin)
        self._gif_colors_label = form.labelForField(self._gif_colors_spin)

        self._gif_dither_check = QCheckBox("Enable dithering")
        self._gif_dither_check.setChecked(ps.gif_dither)
        form.addRow("", self._gif_dither_check)

        self._gif_loop_spin = QSpinBox()
        self._gif_loop_spin.setRange(0, 9999)
        self._gif_loop_spin.setValue(ps.gif_loop)
        form.addRow("GIF Loop:", self._gif_loop_spin)
        self._gif_loop_label = form.labelForField(self._gif_loop_spin)

        self._gif_scale_spin = QSpinBox()
        self._gif_scale_spin.setRange(25, 100)
        self._gif_scale_spin.setValue(int(ps.gif_scale * 100))
        self._gif_scale_spin.setSuffix("%")
        form.addRow("GIF Scale:", self._gif_scale_spin)
        self._gif_scale_label = form.labelForField(self._gif_scale_spin)

        layout.addLayout(form)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status label
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Buttons
        self._button_box = QDialogButtonBox()
        self._export_btn = self._button_box.addButton(
            "Render", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._cancel_btn = self._button_box.addButton(
            QDialogButtonBox.StandardButton.Cancel
        )
        self._export_btn.clicked.connect(self._on_export)
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._button_box)

        # Sync detail widgets: for non-custom presets, fill from preset values;
        # for custom, apply the sidebar's explicit values.
        if ps.quality_preset == "custom":
            self._apply_custom_details_from_settings(ps)
        else:
            self._sync_quality_details_from_preset()
        self._update_visibility()

    def _build_concat_section(self) -> CollapsibleSection:
        """Build the collapsible Intro / Outro section."""
        section = CollapsibleSection("Intro / Outro", expanded=False)
        content = QWidget()
        content_layout = QFormLayout(content)
        content_layout.setContentsMargins(8, 0, 0, 0)

        video_filter = "Video files (*.mp4 *.webm *.mov *.avi *.mkv)"

        # Intro row
        intro_layout = QHBoxLayout()
        self._intro_edit = QLineEdit()
        self._intro_edit.setReadOnly(True)
        self._intro_edit.setPlaceholderText("No intro video")
        intro_layout.addWidget(self._intro_edit)
        intro_browse = QPushButton("Browse")
        intro_browse.clicked.connect(
            lambda: self._browse_clip(self._intro_edit, self._intro_info_label, video_filter)
        )
        intro_layout.addWidget(intro_browse)
        intro_clear = QPushButton("\u2715")
        intro_clear.setFixedWidth(28)
        intro_clear.clicked.connect(lambda: self._clear_clip(self._intro_edit, self._intro_info_label))
        intro_layout.addWidget(intro_clear)
        content_layout.addRow("Intro:", intro_layout)

        self._intro_info_label = QLabel("")
        content_layout.addRow("", self._intro_info_label)

        self._intro_keep_audio = QCheckBox("Keep audio")
        self._intro_keep_audio.setChecked(True)
        content_layout.addRow("", self._intro_keep_audio)

        self._intro_fade_in = self._make_fade_spin()
        content_layout.addRow("Fade in:", self._intro_fade_in)

        self._intro_fade_out = self._make_fade_spin()
        content_layout.addRow("Fade out:", self._intro_fade_out)

        # Outro row
        outro_layout = QHBoxLayout()
        self._outro_edit = QLineEdit()
        self._outro_edit.setReadOnly(True)
        self._outro_edit.setPlaceholderText("No outro video")
        outro_layout.addWidget(self._outro_edit)
        outro_browse = QPushButton("Browse")
        outro_browse.clicked.connect(
            lambda: self._browse_clip(self._outro_edit, self._outro_info_label, video_filter)
        )
        outro_layout.addWidget(outro_browse)
        outro_clear = QPushButton("\u2715")
        outro_clear.setFixedWidth(28)
        outro_clear.clicked.connect(lambda: self._clear_clip(self._outro_edit, self._outro_info_label))
        outro_layout.addWidget(outro_clear)
        content_layout.addRow("Outro:", outro_layout)

        self._outro_info_label = QLabel("")
        content_layout.addRow("", self._outro_info_label)

        self._outro_keep_audio = QCheckBox("Keep audio")
        self._outro_keep_audio.setChecked(True)
        content_layout.addRow("", self._outro_keep_audio)

        self._outro_fade_in = self._make_fade_spin()
        content_layout.addRow("Fade in:", self._outro_fade_in)

        self._outro_fade_out = self._make_fade_spin()
        content_layout.addRow("Fade out:", self._outro_fade_out)

        section.set_content(content)
        return section

    @staticmethod
    def _make_fade_spin() -> QDoubleSpinBox:
        """Create a fade-duration spinbox (0.0–30.0 s, step 0.1)."""
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 30.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(1)
        spin.setSuffix(" s")
        spin.setValue(0.0)
        return spin

    def _browse_clip(self, edit: QLineEdit, info_label: QLabel, file_filter: str) -> None:
        """Open file dialog to select a video clip."""
        path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", file_filter)
        if path:
            edit.setText(path)
            self._probe_and_show_clip_info(Path(path), info_label)

    def _clear_clip(self, edit: QLineEdit, info_label: QLabel) -> None:
        """Clear a selected clip."""
        edit.clear()
        info_label.clear()

    def _probe_and_show_clip_info(self, path: Path, info_label: QLabel) -> None:
        """Probe a video clip and display its metadata."""
        try:
            from wavern.core.video_concat import probe_video_clip

            info = probe_video_clip(path)
            info_label.setText(f"{info.width}x{info.height} @ {info.fps:.1f}fps, {info.duration:.1f}s")
        except ValueError as e:
            info_label.setText(f"Error: {e}")

    def _populate_codec_combo(self, container: str) -> None:
        self._codec_combo.blockSignals(True)
        self._codec_combo.clear()
        codecs = get_codecs_for_container(container)
        for desc in codecs:
            self._codec_combo.addItem(desc.display_name, desc.codec_id)
        self._codec_combo.blockSignals(False)

    def _populate_speed_combo(self, codec_id: str) -> None:
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

    def _apply_custom_details_from_settings(self, ps: ProjectSettings) -> None:
        """Apply explicit CRF/speed/ProRes values from sidebar settings (custom mode)."""
        self._rebuilding = True
        self._crf_spin.setValue(ps.crf)
        idx = self._speed_combo.findData(ps.encoder_speed)
        if idx >= 0:
            self._speed_combo.setCurrentIndex(idx)
        prores = ps.prores_profile
        idx = self._prores_combo.findData(prores)
        if idx >= 0:
            self._prores_combo.setCurrentIndex(idx)
        self._rebuilding = False

    def _sync_quality_details_from_preset(self) -> None:
        """Fill CRF, encoder speed, and ProRes profile from the selected quality preset."""
        preset_key = self._quality_combo.currentData()
        if not preset_key or preset_key == "custom":
            return

        codec_id = self._codec_combo.currentData() or ""

        try:
            settings = get_quality_settings(preset_key, codec_id)
        except ValueError:
            return

        self._rebuilding = True

        if "crf" in settings:
            self._crf_spin.setValue(settings["crf"])
        if "encoder_speed" in settings:
            idx = self._speed_combo.findData(settings["encoder_speed"])
            if idx >= 0:
                self._speed_combo.setCurrentIndex(idx)
        if "prores_profile" in settings:
            idx = self._prores_combo.findData(settings["prores_profile"])
            if idx >= 0:
                self._prores_combo.setCurrentIndex(idx)

        self._rebuilding = False

    def _update_visibility(self) -> None:
        """Show/hide widgets based on current format and codec."""
        container = self._format_combo.currentText()
        codec_id = self._codec_combo.currentData() or ""
        family = get_codec_family(codec_id)
        is_gif = container == "gif"
        is_prores = family == "prores"

        # HW Accel: hide for gif
        self._hw_accel_combo.setVisible(not is_gif)
        if self._hw_accel_label:
            self._hw_accel_label.setVisible(not is_gif)

        # Codec: hide for gif
        self._codec_combo.setVisible(not is_gif)
        if self._codec_label:
            self._codec_label.setVisible(not is_gif)

        # Quality preset: hide for gif
        quality_visible = not is_gif
        self._quality_combo.setVisible(quality_visible)
        quality_label = self._form.labelForField(self._quality_combo)
        if quality_label:
            quality_label.setVisible(quality_visible)

        # CRF: visible for CRF-based codecs (not prores, not gif)
        crf_visible = not is_prores and not is_gif
        self._crf_spin.setVisible(crf_visible)
        if self._crf_label:
            self._crf_label.setVisible(crf_visible)

        # Encoder speed: visible for codecs that have speed options (not prores, not gif)
        speed_visible = not is_prores and not is_gif and self._speed_combo.count() > 0
        self._speed_combo.setVisible(speed_visible)
        if self._speed_label:
            self._speed_label.setVisible(speed_visible)

        # ProRes profile: only for prores
        prores_visible = is_prores
        self._prores_combo.setVisible(prores_visible)
        if self._prores_label:
            self._prores_label.setVisible(prores_visible)

        # Audio: hide for gif
        self._audio_bitrate_combo.setVisible(not is_gif)
        if self._audio_bitrate_label:
            self._audio_bitrate_label.setVisible(not is_gif)

        # Intro / Outro: hide for gif and transparent export
        is_transparent = self._preset.background.type == "none"
        self._concat_section.setVisible(not is_gif and not is_transparent)

        # GIF settings
        self._gif_colors_spin.setVisible(is_gif)
        self._gif_dither_check.setVisible(is_gif)
        self._gif_loop_spin.setVisible(is_gif)
        self._gif_scale_spin.setVisible(is_gif)
        if self._gif_colors_label:
            self._gif_colors_label.setVisible(is_gif)
        if self._gif_loop_label:
            self._gif_loop_label.setVisible(is_gif)
        if self._gif_scale_label:
            self._gif_scale_label.setVisible(is_gif)

    def _on_format_changed(self, new_format: str) -> None:
        """Update codec combo, extension, and visibility when format changes."""
        self._populate_codec_combo(new_format)
        codec_id = self._codec_combo.currentData() or ""
        self._populate_speed_combo(codec_id)
        self._sync_quality_details_from_preset()

        # Update file extension
        current_path = self._output_edit.text().strip()
        if current_path:
            path = Path(current_path)
            new_ext = f".{new_format}"
            if path.suffix.lower() in ALL_EXTENSIONS and path.suffix.lower() != new_ext:
                self._output_edit.setText(str(path.with_suffix(new_ext)))

        self._update_visibility()

    def _on_codec_changed(self) -> None:
        codec_id = self._codec_combo.currentData() or ""
        self._populate_speed_combo(codec_id)
        self._sync_quality_details_from_preset()
        self._update_visibility()

    def _on_quality_preset_changed(self) -> None:
        """Preset combo changed — fill detail widgets from preset values."""
        if self._rebuilding:
            return
        self._sync_quality_details_from_preset()
        self._update_visibility()

    def _on_quality_detail_changed(self) -> None:
        """User manually changed CRF, speed, or ProRes profile — switch to Custom."""
        if self._rebuilding:
            return
        # Find the Custom entry and select it without triggering sync
        for i in range(self._quality_combo.count()):
            if self._quality_combo.itemData(i) == "custom":
                self._rebuilding = True
                self._quality_combo.setCurrentIndex(i)
                self._rebuilding = False
                break

    def _check_clip_mismatches(
        self, intro_path: Path | None, outro_path: Path | None,
    ) -> bool:
        """Check intro/outro for mismatches. Returns True to proceed, False to abort."""
        from wavern.core.video_concat import detect_mismatches, probe_video_clip

        target_res = (self._width_spin.value(), self._height_spin.value())
        target_fps = self._fps_spin.value()
        clips: list[tuple[str, object]] = []
        try:
            if intro_path:
                clips.append(("intro", probe_video_clip(intro_path)))
            if outro_path:
                clips.append(("outro", probe_video_clip(outro_path)))
        except ValueError as e:
            QMessageBox.warning(self, "Clip Error", str(e))
            return False

        mismatches = detect_mismatches(
            clips, target_res, target_fps,  # type: ignore[arg-type]
        )
        if not mismatches:
            return True

        lines = []
        for mm in mismatches:
            parts = []
            if not mm.resolution_match:
                parts.append(
                    f"resolution {mm.clip_resolution[0]}x{mm.clip_resolution[1]}"
                    f" \u2192 {mm.target_resolution[0]}x{mm.target_resolution[1]}"
                )
            if not mm.fps_match:
                parts.append(f"fps {mm.clip_fps:.1f} \u2192 {mm.target_fps}")
            lines.append(f"  {mm.clip_label}: {', '.join(parts)}")

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Clip Mismatch")
        msg_box.setText(
            "The following clips differ from render settings "
            "and will be re-encoded:\n\n" + "\n".join(lines)
        )
        conform_btn = msg_box.addButton("Auto-conform", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton("Adjust Settings", QMessageBox.ButtonRole.RejectRole)
        msg_box.addButton(QMessageBox.StandardButton.Cancel)
        msg_box.setDefaultButton(conform_btn)
        msg_box.exec()
        return msg_box.clickedButton() == conform_btn

    def _on_browse(self) -> None:
        default_dir = Path(__file__).resolve().parents[3] / "video"
        default_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Video",
            str(default_dir),
            "MP4 (*.mp4);;WebM (*.webm);;MOV (*.mov);;GIF (*.gif)",
        )
        if path:
            self._output_edit.setText(path)

    def _on_export(self) -> None:
        output_path = self._output_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Render", "Please specify an output path.")
            return

        container = self._format_combo.currentText()
        has_alpha = self._preset.background.type == "none"
        codec_id = self._codec_combo.currentData() or get_default_codec(container)

        # Alpha check: MP4/GIF don't support alpha
        if has_alpha and not supports_alpha(container, codec_id):
            alpha_containers = []
            if container not in ("webm", "mov"):
                alpha_containers = ["WebM (VP9)", "MOV (ProRes)"]
            msg = (
                f"{container.upper()} ({codec_id}) does not support transparency.\n"
                f"Switch to {' or '.join(alpha_containers)} for alpha render, "
                f"or change the background type."
            )
            QMessageBox.warning(
                self, "Transparent Render", msg,
                QMessageBox.StandardButton.Ok,
            )
            # Auto-switch to webm
            self._format_combo.setCurrentText("webm")
            return

        # Always read values directly from the detail widgets
        crf = self._crf_spin.value()
        encoder_speed = self._speed_combo.currentData() or "medium"
        prores_val = self._prores_combo.currentData()
        prores_profile = prores_val if prores_val is not None else 3
        quality_preset = self._quality_combo.currentData() or "high"

        # Collect intro/outro paths
        intro_path: Path | None = None
        outro_path: Path | None = None
        intro_text = self._intro_edit.text().strip()
        outro_text = self._outro_edit.text().strip()
        if intro_text:
            intro_path = Path(intro_text)
        if outro_text:
            outro_path = Path(outro_text)

        # Mismatch warning
        if intro_path or outro_path:
            if not self._check_clip_mismatches(intro_path, outro_path):
                return

        config = ExportConfig(
            output_path=Path(output_path),
            resolution=(self._width_spin.value(), self._height_spin.value()),
            fps=self._fps_spin.value(),
            video_codec=codec_id,
            container=container,
            crf=crf,
            encoder_speed=encoder_speed,
            quality_preset=quality_preset,
            audio_bitrate=self._audio_bitrate_combo.currentText(),
            prores_profile=prores_profile,
            gif_max_colors=self._gif_colors_spin.value(),
            gif_dither=self._gif_dither_check.isChecked(),
            gif_loop=self._gif_loop_spin.value(),
            gif_scale=self._gif_scale_spin.value() / 100.0,
            hw_accel=self._hw_accel_combo.currentData() or "auto",
            intro_path=intro_path,
            outro_path=outro_path,
            intro_keep_audio=self._intro_keep_audio.isChecked(),
            outro_keep_audio=self._outro_keep_audio.isChecked(),
            intro_fade_in=self._intro_fade_in.value(),
            intro_fade_out=self._intro_fade_out.value(),
            outro_fade_in=self._outro_fade_in.value(),
            outro_fade_out=self._outro_fade_out.value(),
        )

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText("Rendering...")

        logger.info(
            "Export started: %s (%dx%d, %dfps, %s/%s)",
            output_path, config.resolution[0], config.resolution[1],
            config.fps, codec_id, container,
        )

        self._export_start_time = time.monotonic()
        self._worker = ExportWorker(self._audio_path, self._preset, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def reject(self) -> None:
        """Stop any running worker before closing the dialog."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        super().reject()

    def _on_cancel(self) -> None:
        self.reject()

    def _on_progress(self, value: float) -> None:
        self._progress.setValue(int(value * 100))
        self._status_label.setText(f"Rendering... {int(value * 100)}%")

    def _on_finished(self, output_path: str) -> None:
        elapsed = time.monotonic() - self._export_start_time
        minutes, seconds = divmod(int(elapsed), 60)
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        logger.info("Export completed in %s: %s", time_str, output_path)
        self._status_label.setText(f"Done: {output_path}")
        self._export_btn.setEnabled(True)
        msg = QMessageBox(self)
        msg.setWindowTitle("Render Complete")
        msg.setText(f"Video saved to:\n{output_path}\n\nRender time: {time_str}")
        msg.addButton(QMessageBox.StandardButton.Ok)
        open_btn = msg.addButton("Open Directory", QMessageBox.ButtonRole.ActionRole)
        msg.exec()
        if msg.clickedButton() == open_btn:
            parent_dir = str(Path(output_path).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(parent_dir))
        if self._worker is not None:
            self._worker.wait()
        self.accept()

    def _on_error(self, error_msg: str) -> None:
        self._status_label.setText("Render failed")
        self._export_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Render Error", error_msg)

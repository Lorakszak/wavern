"""Export settings dialog — resolution, format, codec, quality."""

import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
)

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
        )

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText("Rendering...")

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
        self._status_label.setText(f"Done: {output_path}")
        self._export_btn.setEnabled(True)
        msg = QMessageBox(self)
        msg.setWindowTitle("Render Complete")
        msg.setText(f"Video saved to:\n{output_path}")
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

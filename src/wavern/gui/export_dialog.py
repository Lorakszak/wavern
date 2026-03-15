"""Export settings dialog — resolution, format, codec, quality."""

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
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

from wavern.core.export import ExportConfig, ExportPipeline
from wavern.presets.schema import Preset, ProjectSettings

logger = logging.getLogger(__name__)


class ExportWorker(QThread):
    """Background thread for video export."""

    progress = Signal(float)
    finished = Signal(str)  # output path
    error = Signal(str)

    def __init__(
        self, audio_path: Path, preset: Preset, config: ExportConfig
    ) -> None:
        super().__init__()
        self._pipeline = ExportPipeline(
            audio_path=audio_path,
            preset=preset,
            export_config=config,
            progress_callback=self._on_progress,
        )

    def run(self) -> None:
        try:
            output = self._pipeline.run()
            self.finished.emit(str(output))
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self) -> None:
        self._pipeline.cancel()

    def _on_progress(self, value: float) -> None:
        self.progress.emit(value)


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

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        ps = self._project_settings

        # Output path — use project settings output_dir or default to ./video/
        output_layout = QHBoxLayout()
        self._output_edit = QLineEdit()
        if ps.output_dir:
            default_dir = Path(ps.output_dir)
        else:
            default_dir = Path(__file__).resolve().parents[3] / "video"
        default_dir.mkdir(exist_ok=True)
        stem = self._audio_path.stem if self._audio_path else "output"
        ext = "webm" if self._preset.background.type == "none" else ps.container
        self._output_edit.setText(str(default_dir / f"{stem}.{ext}"))
        output_layout.addWidget(self._output_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        output_layout.addWidget(browse_btn)
        form.addRow("Output:", output_layout)

        # Resolution — pre-fill from project settings
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

        # FPS — pre-fill from project settings
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(24, 144)
        self._fps_spin.setValue(ps.fps)
        form.addRow("FPS:", self._fps_spin)

        # Format — pre-fill from project settings
        self._format_combo = QComboBox()
        self._format_combo.addItems(["mp4", "webm"])
        # Auto-select webm for transparent background, otherwise use project setting
        if self._preset.background.type == "none":
            self._format_combo.setCurrentText("webm")
        else:
            self._format_combo.setCurrentText(ps.container)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        form.addRow("Format:", self._format_combo)

        # Alpha hint
        if self._preset.background.type == "none":
            alpha_hint = QLabel("Background: none → will render with transparency (WebM)")
            alpha_hint.setObjectName("AlphaHint")
            form.addRow(alpha_hint)

        # CRF — pre-fill from project settings
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(ps.crf)
        form.addRow("Quality (CRF):", self._crf_spin)

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

    def _on_format_changed(self, new_format: str) -> None:
        """Auto-update the output file extension when the format changes."""
        current_path = self._output_edit.text().strip()
        if not current_path:
            return
        path = Path(current_path)
        new_ext = f".{new_format}"
        if path.suffix.lower() in (".mp4", ".webm") and path.suffix.lower() != new_ext:
            self._output_edit.setText(str(path.with_suffix(new_ext)))

    def _on_browse(self) -> None:
        default_dir = Path(__file__).resolve().parents[3] / "video"
        default_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Video",
            str(default_dir),
            "MP4 (*.mp4);;WebM (*.webm)",
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

        # Alpha requires WebM (VP9 supports yuva420p)
        if has_alpha and container == "mp4":
            QMessageBox.warning(
                self,
                "Transparent Render",
                "MP4 (H.264) does not support transparency.\n"
                "Switching to WebM (VP9) for alpha render.",
            )
            container = "webm"
            self._format_combo.setCurrentIndex(
                self._format_combo.findText("webm")
            )

        codec = "libx264" if container == "mp4" else "libvpx-vp9"

        config = ExportConfig(
            output_path=Path(output_path),
            resolution=(self._width_spin.value(), self._height_spin.value()),
            fps=self._fps_spin.value(),
            video_codec=codec,
            container=container,
            crf=self._crf_spin.value(),
        )

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText("Rendering...")

        self._worker = ExportWorker(self._audio_path, self._preset, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        self.reject()

    def _on_progress(self, value: float) -> None:
        self._progress.setValue(int(value * 100))
        self._status_label.setText(f"Rendering... {int(value * 100)}%")

    def _on_finished(self, output_path: str) -> None:
        self._status_label.setText(f"Done: {output_path}")
        self._export_btn.setEnabled(True)
        QMessageBox.information(self, "Render Complete", f"Video saved to:\n{output_path}")
        self.accept()

    def _on_error(self, error_msg: str) -> None:
        self._status_label.setText("Render failed")
        self._export_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Render Error", error_msg)

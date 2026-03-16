"""Background QThread worker for running the export pipeline."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from wavern.core.export import ExportConfig, ExportPipeline
from wavern.presets.schema import Preset


class ExportWorker(QThread):
    """Background thread for video export."""

    progress = Signal(float)
    finished = Signal(str)  # output path
    error = Signal(str)

    def __init__(
        self, audio_path: Path, preset: Preset, config: ExportConfig,
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

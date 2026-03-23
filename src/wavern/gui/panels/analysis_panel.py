"""Analysis settings panel — FFT size, smoothing, beat sensitivity."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


class AnalysisPanel(QWidget):
    """Audio analysis settings: FFT size, smoothing, beat sensitivity."""

    params_changed = Signal(object)  # updated Preset

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False
        self._section_states: dict[str, bool] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = layout

    def set_preset(self, preset: Preset) -> None:
        """Rebuild the analysis panel for the given preset."""
        self._preset = preset
        self._rebuilding = True

        self._save_section_states()

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._analysis_section = CollapsibleSection("Analysis")
        self._build_analysis_section(preset)
        self._content_layout.addWidget(self._analysis_section)

        self._restore_section_states()
        self._rebuilding = False

    def update_values(self, preset: Preset) -> None:
        """Update widget values in-place without rebuilding."""
        if not hasattr(self, "_fft_size_spin"):
            self.set_preset(preset)
            return
        self._preset = preset
        self._rebuilding = True
        for w in (self._fft_size_spin, self._smoothing_spin, self._beat_sens_spin):
            w.blockSignals(True)
        self._fft_size_spin.setValue(preset.fft_size)
        self._smoothing_spin.setValue(preset.smoothing)
        self._beat_sens_spin.setValue(preset.beat_sensitivity)
        for w in (self._fft_size_spin, self._smoothing_spin, self._beat_sens_spin):
            w.blockSignals(False)
        self._rebuilding = False

    def _save_section_states(self) -> None:
        if hasattr(self, "_analysis_section"):
            self._section_states["Analysis"] = self._analysis_section.is_expanded()

    def _restore_section_states(self) -> None:
        if "Analysis" in self._section_states and hasattr(self, "_analysis_section"):
            self._analysis_section.set_expanded(self._section_states["Analysis"])

    def _build_analysis_section(self, preset: Preset) -> None:
        """Build audio analysis settings."""
        analysis_content = QWidget()
        analysis_layout = QFormLayout(analysis_content)
        analysis_layout.setContentsMargins(4, 0, 4, 0)

        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedWidth(90)
        reset_btn.clicked.connect(self._on_reset_all_analysis)
        analysis_layout.addRow("", reset_btn)

        self._fft_size_spin = DragSpinBox(
            minimum=256, maximum=16384, step=256, decimals=0, default_value=2048,
            description=(
                "Number of frequency bins. Higher = finer frequency detail but slower response. "
                "Must be power of 2. 2048=balanced, 4096=detailed, 8192=very detailed."
            ),
        )
        self._fft_size_spin.setValue(preset.fft_size)
        self._fft_size_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("FFT Size:", self._fft_size_spin)

        self._smoothing_spin = DragSpinBox(
            minimum=0.0, maximum=0.99, step=0.05, decimals=2, default_value=0.3,
            description=(
                "Temporal smoothing (0\u20130.99). Higher values make visuals react more slowly. "
                "0=raw, 0.3=moderate, 0.8=very smooth."
            ),
        )
        self._smoothing_spin.setValue(preset.smoothing)
        self._smoothing_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("Smoothing:", self._smoothing_spin)

        self._beat_sens_spin = DragSpinBox(
            minimum=0.1, maximum=5.0, step=0.1, decimals=1, default_value=1.0,
            description=(
                "How easily beats are detected. Lower=only strong beats, "
                "higher=triggers on quiet transients. 1.0=default."
            ),
        )
        self._beat_sens_spin.setValue(preset.beat_sensitivity)
        self._beat_sens_spin.valueChanged.connect(self._on_analysis_changed)
        analysis_layout.addRow("Beat Sensitivity:", self._beat_sens_spin)

        self._analysis_section.set_content(analysis_content)

    def _on_reset_all_analysis(self) -> None:
        """Reset analysis settings to defaults."""
        if self._preset is None or self._rebuilding:
            return
        self._preset.fft_size = 2048
        self._preset.smoothing = 0.3
        self._preset.beat_sensitivity = 1.0
        self.set_preset(self._preset)
        self._emit_update()

    def _on_analysis_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.fft_size = int(self._fft_size_spin.value())
        self._preset.smoothing = self._smoothing_spin.value()
        self._preset.beat_sensitivity = self._beat_sens_spin.value()
        self._emit_update()

    def _emit_update(self) -> None:
        if self._preset is not None:
            self.params_changed.emit(self._preset)

"""Project settings panel — resolution, FPS, format, quality, output directory."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.help_button import make_help_button
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

class ProjectSettingsPanel(QWidget):
    """Panel for project-wide output settings (resolution, FPS, format, quality, output dir)."""

    settings_changed = Signal(object)  # emits ProjectSettings

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

        # --- Resolution ---
        separator_res = QLabel("Resolution")
        separator_res.setStyleSheet("font-weight: bold; color: #888; padding-top: 4px;")
        form.addRow(separator_res)

        # Aspect ratio
        aspect_row = QHBoxLayout()
        self._aspect_combo = QComboBox()
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
        self._res_combo = QComboBox()
        self._populate_resolution_combo("16:9")
        quick_row.addWidget(self._res_combo, stretch=1)
        quick_row.addWidget(make_help_button(
            "Resolution is the pixel dimensions of the output video.\n"
            "Higher resolution = sharper image but larger file and slower export."
        ))
        form.addRow("Preset:", quick_row)

        # Manual width x height
        dim_row = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(320, 7680)
        self._width_spin.setValue(1920)
        dim_row.addWidget(self._width_spin)
        dim_row.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(240, 4320)
        self._height_spin.setValue(1080)
        dim_row.addWidget(self._height_spin)
        form.addRow("Size:", dim_row)

        # --- Frame Rate ---
        separator_fps = QLabel("Frame Rate")
        separator_fps.setStyleSheet("font-weight: bold; color: #888; padding-top: 8px;")
        form.addRow(separator_fps)

        fps_row = QHBoxLayout()
        self._fps_combo = QComboBox()
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

        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 240)
        self._fps_spin.setValue(60)
        form.addRow("Value:", self._fps_spin)

        # --- Format ---
        separator_fmt = QLabel("Format")
        separator_fmt.setStyleSheet("font-weight: bold; color: #888; padding-top: 8px;")
        form.addRow(separator_fmt)

        fmt_row = QHBoxLayout()
        self._format_combo = QComboBox()
        self._format_combo.addItems(["mp4", "webm"])
        fmt_row.addWidget(self._format_combo, stretch=1)
        fmt_row.addWidget(make_help_button(
            "MP4 (H.264): widely compatible, smaller files, no transparency.\n"
            "WebM (VP9): supports transparency, good for overlays."
        ))
        form.addRow("Format:", fmt_row)

        # --- Quality ---
        separator_q = QLabel("Quality")
        separator_q.setStyleSheet("font-weight: bold; color: #888; padding-top: 8px;")
        form.addRow(separator_q)

        crf_row = QHBoxLayout()
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(18)
        crf_row.addWidget(self._crf_spin, stretch=1)
        crf_row.addWidget(make_help_button(
            "CRF (Constant Rate Factor) controls video quality.\n"
            "Lower = better quality, larger file.\n"
            "0 = lossless, 18 = visually lossless, 23 = default, 28+ = noticeable compression."
        ))
        form.addRow("CRF:", crf_row)

        # --- Output Directory ---
        separator_out = QLabel("Output")
        separator_out.setStyleSheet("font-weight: bold; color: #888; padding-top: 8px;")
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

        self._connect_signals()

    def _connect_signals(self) -> None:
        self._aspect_combo.currentTextChanged.connect(self._on_aspect_changed)
        self._res_combo.currentIndexChanged.connect(self._on_res_preset_changed)
        self._width_spin.valueChanged.connect(self._on_dimension_changed)
        self._height_spin.valueChanged.connect(self._on_dimension_changed)
        self._fps_combo.currentIndexChanged.connect(self._on_fps_combo_changed)
        self._fps_spin.valueChanged.connect(self._on_fps_spin_changed)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        self._crf_spin.valueChanged.connect(self._on_crf_changed)
        self._output_edit.textChanged.connect(self._on_output_dir_changed)

    def _populate_resolution_combo(self, aspect: str) -> None:
        """Populate resolution combo for the given aspect ratio."""
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        presets = _RESOLUTION_PRESETS.get(aspect, [])
        for w, h in presets:
            self._res_combo.addItem(f"{w}x{h}", (w, h))
        self._res_combo.blockSignals(False)

    def _on_aspect_changed(self, aspect: str) -> None:
        if aspect == "Custom":
            self._res_combo.setEnabled(False)
            return

        self._res_combo.setEnabled(True)
        self._populate_resolution_combo(aspect)

        if self._res_combo.count() > 0:
            current = (self._width_spin.value(), self._height_spin.value())
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

    def _on_fps_combo_changed(self, index: int) -> None:
        fps_val = self._fps_combo.currentData()
        if fps_val != -1:  # preset selected — sync spinbox
            self._fps_spin.blockSignals(True)
            self._fps_spin.setValue(fps_val)
            self._fps_spin.blockSignals(False)
        self._update_settings()

    def _on_fps_spin_changed(self) -> None:
        value = self._fps_spin.value()
        # Find matching preset and select it, or fall back to Custom
        match_idx = -1
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == value:
                match_idx = i
                break
        self._fps_combo.blockSignals(True)
        if match_idx >= 0:
            self._fps_combo.setCurrentIndex(match_idx)
        else:
            # Select "Custom" entry
            custom_idx = self._fps_combo.findData(-1)
            if custom_idx >= 0:
                self._fps_combo.setCurrentIndex(custom_idx)
        self._fps_combo.blockSignals(False)
        self._update_settings()

    def _on_format_changed(self) -> None:
        self._update_settings()

    def _on_crf_changed(self) -> None:
        self._update_settings()

    def _on_output_dir_changed(self) -> None:
        self._update_settings()

    def _on_browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._output_edit.setText(path)

    def set_format(self, fmt: str) -> None:
        """Programmatically set the container format without emitting settings_changed."""
        self._format_combo.blockSignals(True)
        idx = self._format_combo.findText(fmt)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        self._format_combo.blockSignals(False)
        self._update_settings()

    def _update_settings(self) -> None:
        """Rebuild ProjectSettings from current widget state and emit signal."""
        self._settings = ProjectSettings(
            resolution=(self._width_spin.value(), self._height_spin.value()),
            fps=self._fps_spin.value(),
            container=self._format_combo.currentText(),
            crf=self._crf_spin.value(),
            output_dir=self._output_edit.text().strip(),
        )
        self.settings_changed.emit(self._settings)

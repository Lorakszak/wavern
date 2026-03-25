"""Intro/outro video selection section for the project settings panel."""

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

VIDEO_FILTER = "Video files (*.mp4 *.webm *.mov *.avi *.mkv)"


class IntroOutroSection(QWidget):
    """File pickers and keep-audio toggles for intro/outro clips."""

    intro_outro_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rebuilding = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        separator = QLabel("Intro / Outro")
        separator.setObjectName("SectionSeparator")
        form.addRow(separator)

        # Intro row
        intro_row = QHBoxLayout()
        self._intro_edit = QLineEdit()
        self._intro_edit.setReadOnly(True)
        self._intro_edit.setPlaceholderText("No intro video")
        intro_row.addWidget(self._intro_edit, stretch=1)
        intro_browse = QPushButton("Browse")
        intro_browse.clicked.connect(self._on_browse_intro)
        intro_row.addWidget(intro_browse)
        intro_clear = QPushButton("\u2715")
        intro_clear.setFixedWidth(28)
        intro_clear.clicked.connect(self._on_clear_intro)
        intro_row.addWidget(intro_clear)
        form.addRow("Intro:", intro_row)

        self._intro_info = QLabel("")
        form.addRow("", self._intro_info)

        self._intro_keep_audio = QCheckBox("Keep audio")
        self._intro_keep_audio.setChecked(True)
        self._intro_keep_audio.toggled.connect(self._on_changed)
        form.addRow("", self._intro_keep_audio)

        self._intro_fade_in = self._make_fade_spin()
        self._intro_fade_in.valueChanged.connect(self._on_changed)
        form.addRow("Fade in:", self._intro_fade_in)

        self._intro_fade_out = self._make_fade_spin()
        self._intro_fade_out.valueChanged.connect(self._on_changed)
        form.addRow("Fade out:", self._intro_fade_out)

        # Outro row
        outro_row = QHBoxLayout()
        self._outro_edit = QLineEdit()
        self._outro_edit.setReadOnly(True)
        self._outro_edit.setPlaceholderText("No outro video")
        outro_row.addWidget(self._outro_edit, stretch=1)
        outro_browse = QPushButton("Browse")
        outro_browse.clicked.connect(self._on_browse_outro)
        outro_row.addWidget(outro_browse)
        outro_clear = QPushButton("\u2715")
        outro_clear.setFixedWidth(28)
        outro_clear.clicked.connect(self._on_clear_outro)
        outro_row.addWidget(outro_clear)
        form.addRow("Outro:", outro_row)

        self._outro_info = QLabel("")
        form.addRow("", self._outro_info)

        self._outro_keep_audio = QCheckBox("Keep audio")
        self._outro_keep_audio.setChecked(True)
        self._outro_keep_audio.toggled.connect(self._on_changed)
        form.addRow("", self._outro_keep_audio)

        self._outro_fade_in = self._make_fade_spin()
        self._outro_fade_in.valueChanged.connect(self._on_changed)
        form.addRow("Fade in:", self._outro_fade_in)

        self._outro_fade_out = self._make_fade_spin()
        self._outro_fade_out.valueChanged.connect(self._on_changed)
        form.addRow("Fade out:", self._outro_fade_out)

        layout.addLayout(form)

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

    def collect(self) -> dict:
        """Return current intro/outro settings as a dict."""
        return {
            "intro_path": self._intro_edit.text().strip(),
            "outro_path": self._outro_edit.text().strip(),
            "intro_keep_audio": self._intro_keep_audio.isChecked(),
            "outro_keep_audio": self._outro_keep_audio.isChecked(),
            "intro_fade_in": self._intro_fade_in.value(),
            "intro_fade_out": self._intro_fade_out.value(),
            "outro_fade_in": self._outro_fade_in.value(),
            "outro_fade_out": self._outro_fade_out.value(),
        }

    def reset(self) -> None:
        """Clear all intro/outro selections."""
        self._rebuilding = True
        self._intro_edit.clear()
        self._intro_info.clear()
        self._intro_keep_audio.setChecked(True)
        self._intro_fade_in.setValue(0.0)
        self._intro_fade_out.setValue(0.0)
        self._outro_edit.clear()
        self._outro_info.clear()
        self._outro_keep_audio.setChecked(True)
        self._outro_fade_in.setValue(0.0)
        self._outro_fade_out.setValue(0.0)
        self._rebuilding = False

    def update_values(
        self,
        intro_path: str,
        outro_path: str,
        intro_keep_audio: bool,
        outro_keep_audio: bool,
        intro_fade_in: float = 0.0,
        intro_fade_out: float = 0.0,
        outro_fade_in: float = 0.0,
        outro_fade_out: float = 0.0,
    ) -> None:
        """Sync widget state from external values (e.g. dual sidebar sync)."""
        self._rebuilding = True
        self._intro_edit.setText(intro_path)
        if intro_path:
            self._probe_clip(Path(intro_path), self._intro_info)
        else:
            self._intro_info.clear()
        self._intro_keep_audio.setChecked(intro_keep_audio)
        self._intro_fade_in.setValue(intro_fade_in)
        self._intro_fade_out.setValue(intro_fade_out)

        self._outro_edit.setText(outro_path)
        if outro_path:
            self._probe_clip(Path(outro_path), self._outro_info)
        else:
            self._outro_info.clear()
        self._outro_keep_audio.setChecked(outro_keep_audio)
        self._outro_fade_in.setValue(outro_fade_in)
        self._outro_fade_out.setValue(outro_fade_out)
        self._rebuilding = False

    # --- Internal callbacks ---

    def _on_changed(self) -> None:
        if self._rebuilding:
            return
        self.intro_outro_changed.emit()

    def _on_browse_intro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Intro Video", "", VIDEO_FILTER)
        if path:
            self._intro_edit.setText(path)
            self._probe_clip(Path(path), self._intro_info)
            self._on_changed()

    def _on_clear_intro(self) -> None:
        self._intro_edit.clear()
        self._intro_info.clear()
        self._on_changed()

    def _on_browse_outro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Outro Video", "", VIDEO_FILTER)
        if path:
            self._outro_edit.setText(path)
            self._probe_clip(Path(path), self._outro_info)
            self._on_changed()

    def _on_clear_outro(self) -> None:
        self._outro_edit.clear()
        self._outro_info.clear()
        self._on_changed()

    def _probe_clip(self, path: Path, info_label: QLabel) -> None:
        """Probe a video clip and display its metadata."""
        try:
            from wavern.core.video_concat import probe_video_clip

            info = probe_video_clip(path)
            info_label.setText(
                f"{info.width}x{info.height} @ {info.fps:.1f}fps, {info.duration:.1f}s"
            )
        except ValueError as e:
            info_label.setText(f"Error: {e}")

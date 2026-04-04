"""Project settings panel — thin coordinator for resolution, quality, and output sections."""

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.help_button import make_help_button
from wavern.gui.panels.intro_outro_section import IntroOutroSection
from wavern.gui.panels.quality_section import QualitySection
from wavern.gui.panels.resolution_section import ResolutionSection
from wavern.presets.schema import ProjectSettings

logger = logging.getLogger(__name__)


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Reset All ---
        reset_form = QFormLayout()
        reset_form.setContentsMargins(4, 0, 4, 0)
        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedWidth(90)
        reset_btn.clicked.connect(self._on_reset_all)
        reset_form.addRow("", reset_btn)
        layout.addLayout(reset_form)

        # --- Resolution & FPS ---
        self._resolution_section = ResolutionSection()
        self._resolution_section.resolution_changed.connect(self._on_setting_changed)
        layout.addWidget(self._resolution_section)

        # --- Format, Codec, Quality, Audio, GIF ---
        self._quality_section = QualitySection()
        self._quality_section.quality_changed.connect(self._on_setting_changed)
        layout.addWidget(self._quality_section)

        # --- Intro / Outro ---
        self._intro_outro_section = IntroOutroSection()
        self._intro_outro_section.intro_outro_changed.connect(self._on_setting_changed)
        layout.addWidget(self._intro_outro_section)

        # --- Output Directory ---
        out_form = QFormLayout()
        out_form.setContentsMargins(4, 0, 4, 0)

        separator_out = QLabel("Output")
        separator_out.setObjectName("SectionSeparator")
        out_form.addRow(separator_out)

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
        out_form.addRow("Directory:", out_row)

        filename_row = QHBoxLayout()
        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText("Default: derived from audio file")
        filename_row.addWidget(self._filename_edit, stretch=1)
        filename_row.addWidget(make_help_button(
            "Output filename (without extension).\n"
            "Leave empty to use the audio file name."
        ))
        out_form.addRow("Filename:", filename_row)

        export_btn = QPushButton("Export")
        export_btn.setObjectName("ExportButton")
        export_btn.clicked.connect(self.export_requested)
        out_form.addRow(export_btn)

        layout.addLayout(out_form)

        self._output_edit.textChanged.connect(self._on_setting_changed)
        self._filename_edit.textChanged.connect(self._on_setting_changed)

    # --- Callbacks ---

    def _on_setting_changed(self) -> None:
        if self._rebuilding:
            return
        self._update_settings()

    def _on_browse_output(self) -> None:
        default_dir = str(Path.home() / "Videos")
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", default_dir,
        )
        if path:
            self._output_edit.setText(path)

    def _on_reset_all(self) -> None:
        """Reset all export settings to defaults."""
        defaults = ProjectSettings()
        self._rebuilding = True

        self._resolution_section.reset(defaults)
        self._quality_section.reset(defaults)
        self._intro_outro_section.reset()

        self._output_edit.setText(defaults.output_dir)
        self._filename_edit.setText(defaults.output_filename)

        self._rebuilding = False
        self._update_settings()

    # --- Public API ---

    def set_alpha_mode(self, enabled: bool) -> None:
        """Enable/disable alpha-only format restrictions.

        Args:
            enabled: True when background is transparent ("none").
        """
        self._quality_section.set_alpha_mode(enabled)

    def set_format(self, fmt: str) -> None:
        """Programmatically set the container format.

        Args:
            fmt: Container format string (e.g. "mp4", "webm").
        """
        self._quality_section.set_format(fmt)
        self._update_settings()

    def set_audio_metadata(self, bitrate: int | None) -> None:
        """Update the source audio bitrate info label.

        Args:
            bitrate: Source audio bitrate in kbps, or None if unknown.
        """
        self._quality_section.set_audio_metadata(bitrate)

    def update_values(self, settings: ProjectSettings) -> None:
        """Sync widget state from external settings (dual sidebar sync).

        Args:
            settings: ProjectSettings to sync from.
        """
        if self._rebuilding:
            return
        self._rebuilding = True
        self._resolution_section.update_values(settings)
        self._quality_section.update_values(settings)
        self._intro_outro_section.update_values(
            intro_path=settings.intro_path,
            outro_path=settings.outro_path,
            intro_keep_audio=settings.intro_keep_audio,
            outro_keep_audio=settings.outro_keep_audio,
            intro_fade_in=settings.intro_fade_in,
            intro_fade_out=settings.intro_fade_out,
            outro_fade_in=settings.outro_fade_in,
            outro_fade_out=settings.outro_fade_out,
        )
        self._output_edit.blockSignals(True)
        self._filename_edit.blockSignals(True)
        self._output_edit.setText(settings.output_dir)
        self._filename_edit.setText(settings.output_filename)
        self._output_edit.blockSignals(False)
        self._filename_edit.blockSignals(False)
        self._settings = settings
        self._rebuilding = False

    # --- Settings assembly ---

    def _update_settings(self) -> None:
        """Rebuild ProjectSettings from section widgets and emit signal."""
        res_data = self._resolution_section.collect()
        quality_data = self._quality_section.collect()
        intro_outro_data = self._intro_outro_section.collect()

        self._settings = ProjectSettings(
            resolution=res_data["resolution"],
            fps=res_data["fps"],
            output_dir=self._output_edit.text().strip(),
            output_filename=self._filename_edit.text().strip(),
            **quality_data,
            **intro_outro_data,
        )
        self.settings_changed.emit(self._settings)

"""Main application window — orchestrates all GUI components."""

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoadError, AudioLoader
from wavern.core.audio_player import AudioPlayer
from wavern.gui.export_dialog import ExportDialog
from wavern.gui.file_import_dialog import open_audio_file
from wavern.gui.gl_widget import GLPreviewWidget
from wavern.gui.preset_panel import PresetPanel
from wavern.gui.settings_panel import SettingsPanel
from wavern.gui.transport_bar import TransportBar
from wavern.presets.manager import PresetManager
from wavern.presets.schema import Preset, VisualizationParams

logger = logging.getLogger(__name__)

# Default preset to load on startup
DEFAULT_PRESET = Preset(
    name="Default",
    visualization=VisualizationParams(
        visualization_type="spectrum_bars",
        params={"bar_count": 64, "mirror": True},
    ),
    color_palette=["#00FFAA", "#FF00AA", "#FFAA00"],
    background={"type": "solid", "color": "#0A0A0F"},
)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(
        self,
        audio_path: Path | None = None,
        preset_name: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Wavern — Music Visualizer")
        self.setMinimumSize(1100, 700)

        icon_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
        pixmap = QPixmap(str(icon_path))
        self.setWindowIcon(QIcon(pixmap))

        self._audio_path: Path | None = None
        self._audio_data: np.ndarray | None = None
        self._sample_rate: int = 44100

        self._player = AudioPlayer()
        self._analyzer = AudioAnalyzer()
        self._preset_manager = PresetManager()

        self._setup_menu()
        self._setup_ui()
        self._connect_signals()

        # Load initial preset
        preset = DEFAULT_PRESET
        if preset_name:
            try:
                preset = self._preset_manager.load(preset_name)
            except Exception as e:
                logger.warning("Could not load preset '%s': %s", preset_name, e)

        self._apply_preset(preset)

        # Load audio if provided
        if audio_path:
            self._load_audio(audio_path)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        import_action = QAction("Import Audio...", self)
        import_action.setShortcut("Ctrl+O")
        import_action.triggered.connect(self._on_import_audio)
        file_menu.addAction(import_action)

        export_action = QAction("Export Video...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export_video)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Splitter: sidebar | center
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left sidebar
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)

        self._preset_panel = PresetPanel(self._preset_manager)
        sidebar_layout.addWidget(self._preset_panel, stretch=1)

        self._settings_panel = SettingsPanel()
        sidebar_layout.addWidget(self._settings_panel, stretch=2)

        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(400)
        splitter.addWidget(sidebar)

        # Center area (GL preview + transport)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self._gl_widget = GLPreviewWidget()
        center_layout.addWidget(self._gl_widget, stretch=1)

        self._transport = TransportBar()
        center_layout.addWidget(self._transport)

        splitter.addWidget(center)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # Position update timer
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(50)  # 20 Hz
        self._position_timer.timeout.connect(self._update_position)

    def _connect_signals(self) -> None:
        self._preset_panel.preset_selected.connect(self._on_preset_selected)
        self._settings_panel.params_changed.connect(self._on_params_changed)
        self._transport.play_clicked.connect(self._on_play)
        self._transport.pause_clicked.connect(self._on_pause)
        self._transport.seek_requested.connect(self._on_seek)

    def _load_audio(self, path: Path) -> None:
        """Load an audio file and configure the pipeline."""
        try:
            audio_data, metadata = AudioLoader.load(str(path))
        except AudioLoadError as e:
            QMessageBox.critical(self, "Load Error", str(e))
            return

        self._audio_path = path
        self._audio_data = audio_data
        self._sample_rate = metadata.sample_rate

        self._player.load(audio_data, metadata.sample_rate)
        self._analyzer.configure(audio_data, metadata.sample_rate)

        self._gl_widget.set_analyzer(self._analyzer)
        self._gl_widget.set_player(self._player)

        self._transport.set_duration(metadata.duration)

        self.setWindowTitle(f"Wavern — {path.name}")
        logger.info("Loaded audio: %s (%.1fs)", path.name, metadata.duration)

    def _apply_preset(self, preset: Preset) -> None:
        """Apply a preset to all components."""
        self._gl_widget.set_preset(preset)
        self._settings_panel.set_preset(preset)
        self._preset_panel.set_current_preset(preset)

    def _on_import_audio(self) -> None:
        path = open_audio_file(self)
        if path:
            self._load_audio(path)

    def _on_export_video(self) -> None:
        if self._audio_path is None:
            QMessageBox.information(self, "Export", "Import an audio file first.")
            return

        preset = self._settings_panel._preset
        if preset is None:
            preset = DEFAULT_PRESET

        dialog = ExportDialog(self._audio_path, preset, self)
        dialog.exec()

    def _on_preset_selected(self, preset: Preset) -> None:
        self._apply_preset(preset)

    def _on_params_changed(self, preset: Preset) -> None:
        self._gl_widget.update_preset(preset)
        self._preset_panel.set_current_preset(preset)

    def _on_play(self) -> None:
        if self._audio_data is None:
            QMessageBox.information(self, "Playback", "Import an audio file first.")
            return
        self._player.play()
        self._gl_widget.start_preview()
        self._transport.set_playing(True)
        self._position_timer.start()

    def _on_pause(self) -> None:
        self._player.pause()
        self._gl_widget.stop_preview()
        self._transport.set_playing(False)
        self._position_timer.stop()

    def _on_seek(self, timestamp: float) -> None:
        self._player.seek(timestamp)

    def _update_position(self) -> None:
        """Sync transport bar with player position."""
        pos = self._player.get_position()
        self._transport.update_position(pos)

        if not self._player.is_playing:
            self._on_pause()

    def closeEvent(self, event) -> None:
        """Cleanup on window close."""
        self._player.stop()
        self._gl_widget.stop_preview()
        self._gl_widget.cleanup()
        super().closeEvent(event)

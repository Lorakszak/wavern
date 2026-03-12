"""Main application window — orchestrates all GUI components."""

import copy
import logging
import re
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QLineEdit
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoadError, AudioLoader
from wavern.core.audio_player import AudioPlayer
from wavern.gui.collapsible_section import CollapsibleSection
from wavern.gui.export_dialog import ExportDialog
from wavern.gui.file_import_dialog import open_audio_file
from wavern.gui.gl_widget import GLPreviewWidget
from wavern.gui.preset_panel import PresetPanel
from wavern.gui.project_settings_panel import ProjectSettingsPanel
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
        self._prev_format: str = "mp4"  # restored when bg changes away from "none"
        self._bg_type: str = ""  # last known background type

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

        # Start maximized
        self.showMaximized()

        # Application-level event filter so transport keys work regardless of focus
        QApplication.instance().installEventFilter(self)

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

        export_action = QAction("Render Video...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export_video)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        file_menu.addSeparator()

        save_preset_action = QAction("Save Preset", self)
        save_preset_action.setShortcut("Ctrl+S")
        save_preset_action.triggered.connect(self._on_save_preset)
        file_menu.addAction(save_preset_action)

        save_preset_as_action = QAction("Save Preset As…", self)
        save_preset_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_preset_as_action.triggered.connect(self._on_save_preset_as)
        file_menu.addAction(save_preset_as_action)

        # View menu
        view_menu = menubar.addMenu("View")

        self._toggle_sidebar_action = QAction("Toggle Sidebar", self)
        self._toggle_sidebar_action.setShortcut("Ctrl+B")
        self._toggle_sidebar_action.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self._toggle_sidebar_action)

        fullscreen_action = QAction("Fullscreen Preview", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self._on_toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # Visualization shortcuts (Ctrl+1…5)
        viz_menu = menubar.addMenu("Visualization")
        for i in range(1, 6):
            action = QAction(f"Switch to Visualization {i}", self)
            action.setShortcut(f"Ctrl+{i}")
            action.setData(i - 1)
            action.triggered.connect(self._on_viz_shortcut)
            viz_menu.addAction(action)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar container (scroll area with all panels)
        self._sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Presets section
        self._preset_panel = PresetPanel(self._preset_manager)
        self._preset_section = CollapsibleSection("Presets")
        self._preset_section.set_content(self._preset_panel)
        scroll_layout.addWidget(self._preset_section)

        # Project settings — single collapsible section
        self._project_settings_panel = ProjectSettingsPanel()
        self._project_section = CollapsibleSection("Project Settings")
        self._project_section.set_content(self._project_settings_panel)
        scroll_layout.addWidget(self._project_section)

        # Visualization settings (sections are already collapsible internally)
        self._settings_panel = SettingsPanel()
        scroll_layout.addWidget(self._settings_panel)

        scroll.setWidget(scroll_content)
        sidebar_layout.addWidget(scroll)

        self._sidebar.setMinimumWidth(250)

        # Sidebar toggle button
        self._toggle_btn = QPushButton("\u25C0")
        self._toggle_btn.setFixedWidth(20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { border: none; background: #2a2a2a; color: #aaa; font-size: 10px; }"
            "QPushButton:hover { background: #444; color: #fff; }"
        )
        self._toggle_btn.clicked.connect(self._toggle_sidebar)
        self._toggle_btn.setToolTip("Toggle Sidebar (Ctrl+B)")

        # Center area (GL preview + transport)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self._gl_widget = GLPreviewWidget()
        center_layout.addWidget(self._gl_widget, stretch=1)

        self._transport = TransportBar()
        center_layout.addWidget(self._transport)

        # Draggable splitter between sidebar and center
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(center)
        self._splitter.setStretchFactor(0, 0)  # sidebar: don't stretch on resize
        self._splitter.setStretchFactor(1, 1)  # center: take remaining space
        self._splitter.setSizes([350, 750])

        # Assemble: toggle button | splitter(sidebar | center)
        main_layout.addWidget(self._toggle_btn)
        main_layout.addWidget(self._splitter, stretch=1)

        # Position update timer
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(50)  # 20 Hz
        self._position_timer.timeout.connect(self._update_position)

    def _toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        visible = self._sidebar.isVisible()
        self._sidebar.setVisible(not visible)
        self._toggle_btn.setText("\u25B6" if visible else "\u25C0")

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
        self._sync_format_to_background(preset.background.type)

    def _prompt_import_audio(self, context: str) -> bool:
        """Show 'no audio' dialog with an Import Audio button. Returns True if audio was loaded."""
        msg = QMessageBox(self)
        msg.setWindowTitle(context)
        msg.setText("Import an audio file first.")
        msg.addButton(QMessageBox.StandardButton.Ok)
        import_btn = msg.addButton("Import Audio", QMessageBox.ButtonRole.ActionRole)
        msg.exec()
        if msg.clickedButton() == import_btn:
            self._on_import_audio()
            return self._audio_data is not None
        return False

    def _on_import_audio(self) -> None:
        path = open_audio_file(self)
        if path:
            self._load_audio(path)

    def _on_export_video(self) -> None:
        if self._audio_path is None:
            if self._prompt_import_audio("Export"):
                return  # audio loaded, but user still needs to re-trigger export
            return

        preset = self._settings_panel._preset
        if preset is None:
            preset = DEFAULT_PRESET

        project_settings = self._project_settings_panel.settings
        dialog = ExportDialog(self._audio_path, preset, project_settings, self)
        dialog.exec()

    def _on_preset_selected(self, preset: Preset) -> None:
        self._apply_preset(preset)

    def _on_params_changed(self, preset: Preset) -> None:
        self._gl_widget.update_preset(preset)
        self._preset_panel.set_current_preset(preset)
        self._sync_format_to_background(preset.background.type)

    def _sync_format_to_background(self, bg_type: str) -> None:
        """Force webm when background is transparent; restore previous format otherwise."""
        if bg_type == self._bg_type:
            return
        prev_bg = self._bg_type
        self._bg_type = bg_type
        if bg_type == "none":
            self._prev_format = self._project_settings_panel.settings.container
            self._project_settings_panel.set_format("webm")
        elif prev_bg == "none":
            self._project_settings_panel.set_format(self._prev_format)

    def _on_play(self) -> None:
        if self._audio_data is None:
            self._prompt_import_audio("Playback")
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

    def eventFilter(self, obj, event) -> bool:
        """Application-level key filter for transport shortcuts."""
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        focused = QApplication.focusWidget()
        input_focused = isinstance(focused, (QAbstractSpinBox, QLineEdit, QComboBox))
        if input_focused:
            return super().eventFilter(obj, event)

        key = event.key()
        mods = event.modifiers()

        # Space → play/pause
        if key == Qt.Key.Key_Space:
            self._transport._on_play_clicked()
            return True

        # Home → go to start
        if key == Qt.Key.Key_Home:
            self._on_seek(0.0)
            self._transport.update_position(0.0)
            return True

        # Left / vim-h → seek backward
        if key in (Qt.Key.Key_Left, Qt.Key.Key_H):
            step = 1.0 if mods & Qt.KeyboardModifier.ShiftModifier else 5.0
            pos = max(0.0, self._player.get_position() - step)
            self._on_seek(pos)
            self._transport.update_position(pos)
            return True

        # Right / vim-l → seek forward
        if key in (Qt.Key.Key_Right, Qt.Key.Key_L):
            step = 1.0 if mods & Qt.KeyboardModifier.ShiftModifier else 5.0
            duration = self._player.duration
            pos = self._player.get_position() + step
            if duration > 0:
                pos = min(duration, pos)
            self._on_seek(pos)
            self._transport.update_position(pos)
            return True

        return super().eventFilter(obj, event)

    def _on_save_preset(self) -> None:
        """Save a copy of the current preset with the lowest available numbered name."""
        preset = self._settings_panel._preset
        if preset is None:
            return

        # Strip trailing digits to get the root base name (e.g. "Default3" → "Default")
        base = re.sub(r'\d+$', '', preset.name) or preset.name

        existing = {info["name"] for info in self._preset_manager.list_presets()}

        # Collect all suffix numbers already used for this base
        used: set[int] = set()
        for name in existing:
            if name.startswith(base):
                suffix = name[len(base):]
                if suffix.isdigit() and suffix:
                    used.add(int(suffix))

        # Find lowest N >= 1 not already taken
        n = 1
        while n in used:
            n += 1

        new_preset = copy.deepcopy(preset)
        new_preset.name = f"{base}{n}"
        try:
            self._preset_manager.save(new_preset)
            self._preset_panel.refresh_list()
            self._preset_panel.set_current_preset(new_preset)
        except Exception as e:
            QMessageBox.critical(self, "Save Preset", str(e))

    def _on_save_preset_as(self) -> None:
        """Delegate to the preset panel's save flow."""
        self._preset_panel._on_save()

    def _on_toggle_fullscreen(self) -> None:
        """Toggle fullscreen state of the main window."""
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _on_viz_shortcut(self) -> None:
        """Switch visualization type via Ctrl+1…5."""
        action = self.sender()
        if action is None:
            return
        index = action.data()
        self._settings_panel.set_viz_by_index(index)

    def closeEvent(self, event) -> None:
        """Cleanup on window close."""
        QApplication.instance().removeEventFilter(self)
        self._player.stop()
        self._gl_widget.stop_preview()
        self._gl_widget.cleanup()
        super().closeEvent(event)

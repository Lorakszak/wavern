"""Main application window — orchestrates all GUI components."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoadError, AudioLoader
from wavern.core.audio_player import AudioPlayer
from wavern.gui.export_dialog import ExportDialog
from wavern.gui.favorites_store import FavoritesStore
from wavern.gui.file_import_dialog import open_audio_file
from wavern.gui.gl_widget import GLPreviewWidget
from wavern.gui.panels import AnalysisPanel, TextPanel, VisualPanel
from wavern.gui.preset_panel import PresetPanel
from wavern.gui.project_settings_panel import ProjectSettingsPanel
from wavern.gui.sidebar import SidebarWidget
from wavern.gui.theme_manager import ThemeManager
from wavern.gui.transport_bar import TransportBar
from wavern.presets.manager import PresetManager
from wavern.presets.schema import Preset, VisualizationParams
from wavern.visualizations.registry import VisualizationRegistry

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
        self._favorites_store = FavoritesStore()
        self._theme_manager = ThemeManager()

        self._bg_type: str = ""  # last known background type
        self._was_maximized: bool = False  # state before entering fullscreen

        # Shared viz memory between both sidebars' VisualPanels
        self._viz_memory: dict[str, dict[str, Any]] = {}

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
        self.menuBar().setNativeMenuBar(False)
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

        save_preset_action = QAction("Save Preset As…", self)
        save_preset_action.setShortcut("Ctrl+S")
        save_preset_action.triggered.connect(self._on_save_preset_as)
        file_menu.addAction(save_preset_action)

        # View menu
        view_menu = menubar.addMenu("View")

        self._toggle_left_action = QAction("Toggle Left Sidebar", self)
        self._toggle_left_action.setShortcut("Ctrl+B")
        self._toggle_left_action.triggered.connect(self._toggle_left_sidebar)
        view_menu.addAction(self._toggle_left_action)

        self._toggle_right_action = QAction("Toggle Right Sidebar", self)
        self._toggle_right_action.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self._toggle_right_action.triggered.connect(self._toggle_right_sidebar)
        view_menu.addAction(self._toggle_right_action)

        view_menu.addSeparator()

        self._split_left_action = QAction("Split Left Sidebar", self)
        self._split_left_action.setCheckable(True)
        self._split_left_action.triggered.connect(self._toggle_split_left)
        view_menu.addAction(self._split_left_action)

        self._split_right_action = QAction("Split Right Sidebar", self)
        self._split_right_action.setCheckable(True)
        self._split_right_action.triggered.connect(self._toggle_split_right)
        view_menu.addAction(self._split_right_action)

        view_menu.addSeparator()

        fullscreen_action = QAction("Fullscreen Preview", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self._on_toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        current_theme = self._theme_manager.load_preference()
        for theme_name in self._theme_manager.list_themes():
            action = QAction(theme_name.capitalize(), self)
            action.setCheckable(True)
            action.setData(theme_name)
            if theme_name == current_theme:
                action.setChecked(True)
            action.triggered.connect(self._on_theme_selected)
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # Visualization shortcuts (Ctrl+1…N, one per registered visualization)
        # Order matches the sidebar combo (list_all insertion order) so indices align.
        viz_menu = menubar.addMenu("Visualization")
        import wavern.visualizations  # noqa: F401 — triggers @register decorators
        viz_infos = VisualizationRegistry().list_all()
        for i, info in enumerate(viz_infos, start=1):
            if i > 9:
                break  # Ctrl+0–9 is the practical limit
            action = QAction(f"Switch to {info['display_name']} (Ctrl+{i})", self)
            action.setShortcut(f"Ctrl+{i}")
            action.setData(i - 1)
            action.triggered.connect(self._on_viz_shortcut)
            viz_menu.addAction(action)

    def _create_sidebar(self, side: str) -> SidebarWidget:
        """Create a SidebarWidget with all 5 tabs populated.

        Args:
            side: "left" or "right" — used to store panel references.
        """
        sidebar = SidebarWidget()
        sidebar.setMinimumWidth(430)

        # Visual panel — shared viz memory dict
        visual = VisualPanel(viz_memory=self._viz_memory)
        sidebar.add_tab("Visual", visual)

        # Text panel
        text = TextPanel()
        sidebar.add_tab("Text", text)

        # Export panel (ProjectSettingsPanel)
        export = ProjectSettingsPanel()
        sidebar.add_tab("Export", export)

        # Presets panel
        presets = PresetPanel(self._preset_manager, self._favorites_store)
        sidebar.add_tab("Presets", presets)

        # Analysis panel
        analysis = AnalysisPanel()
        sidebar.add_tab("Analysis", analysis)

        # Lower-pane tabs (duplicates for split mode)
        visual_lower = VisualPanel(viz_memory=self._viz_memory)
        sidebar.add_lower_tab("Visual", visual_lower)

        text_lower = TextPanel()
        sidebar.add_lower_tab("Text", text_lower)

        export_lower = ProjectSettingsPanel()
        sidebar.add_lower_tab("Export", export_lower)

        presets_lower = PresetPanel(self._preset_manager, self._favorites_store)
        sidebar.add_lower_tab("Presets", presets_lower)

        analysis_lower = AnalysisPanel()
        sidebar.add_lower_tab("Analysis", analysis_lower)

        # Store references keyed by side
        panels = {
            "visual": visual,
            "text": text,
            "export": export,
            "presets": presets,
            "analysis": analysis,
            "visual_lower": visual_lower,
            "text_lower": text_lower,
            "export_lower": export_lower,
            "presets_lower": presets_lower,
            "analysis_lower": analysis_lower,
        }
        setattr(self, f"_{side}_panels", panels)
        return sidebar

    def _all_visual_panels(self) -> list[VisualPanel]:
        """Return all VisualPanel instances across both sidebars."""
        panels: list[VisualPanel] = []
        for side in ("left", "right"):
            p = getattr(self, f"_{side}_panels", {})
            for key in ("visual", "visual_lower"):
                if key in p:
                    panels.append(p[key])
        return panels

    def _all_text_panels(self) -> list[TextPanel]:
        panels: list[TextPanel] = []
        for side in ("left", "right"):
            p = getattr(self, f"_{side}_panels", {})
            for key in ("text", "text_lower"):
                if key in p:
                    panels.append(p[key])
        return panels

    def _all_analysis_panels(self) -> list[AnalysisPanel]:
        panels: list[AnalysisPanel] = []
        for side in ("left", "right"):
            p = getattr(self, f"_{side}_panels", {})
            for key in ("analysis", "analysis_lower"):
                if key in p:
                    panels.append(p[key])
        return panels

    def _all_preset_panels(self) -> list[PresetPanel]:
        panels: list[PresetPanel] = []
        for side in ("left", "right"):
            p = getattr(self, f"_{side}_panels", {})
            for key in ("presets", "presets_lower"):
                if key in p:
                    panels.append(p[key])
        return panels

    def _all_export_panels(self) -> list[ProjectSettingsPanel]:
        panels: list[ProjectSettingsPanel] = []
        for side in ("left", "right"):
            p = getattr(self, f"_{side}_panels", {})
            for key in ("export", "export_lower"):
                if key in p:
                    panels.append(p[key])
        return panels

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar
        self._left_sidebar = self._create_sidebar("left")

        # Right sidebar (hidden by default)
        self._right_sidebar = self._create_sidebar("right")
        self._right_sidebar.setVisible(False)

        # Left toggle button (vertically centered via stretch)
        self._left_toggle_btn = QPushButton("\u25C0")
        self._left_toggle_btn.setObjectName("SidebarToggle")
        self._left_toggle_btn.setFixedWidth(20)
        self._left_toggle_btn.setMinimumHeight(80)
        self._left_toggle_btn.clicked.connect(self._toggle_left_sidebar)
        self._left_toggle_btn.setToolTip("Toggle Left Sidebar (Ctrl+B)")

        left_strip = QWidget()
        left_strip.setFixedWidth(20)
        left_strip_layout = QVBoxLayout(left_strip)
        left_strip_layout.setContentsMargins(0, 0, 0, 0)
        left_strip_layout.setSpacing(0)
        left_strip_layout.addStretch()
        left_strip_layout.addWidget(self._left_toggle_btn)
        left_strip_layout.addStretch()

        # Right toggle button (vertically centered via stretch)
        self._right_toggle_btn = QPushButton("\u25B6")
        self._right_toggle_btn.setObjectName("SidebarToggle")
        self._right_toggle_btn.setFixedWidth(20)
        self._right_toggle_btn.setMinimumHeight(80)
        self._right_toggle_btn.clicked.connect(self._toggle_right_sidebar)
        self._right_toggle_btn.setToolTip("Toggle Right Sidebar (Ctrl+Shift+B)")

        right_strip = QWidget()
        right_strip.setFixedWidth(20)
        right_strip_layout = QVBoxLayout(right_strip)
        right_strip_layout.setContentsMargins(0, 0, 0, 0)
        right_strip_layout.setSpacing(0)
        right_strip_layout.addStretch()
        right_strip_layout.addWidget(self._right_toggle_btn)
        right_strip_layout.addStretch()

        # Split sidebar buttons (placed at bottom of each sidebar)
        self._left_split_btn = QPushButton("Split Sidebar")
        self._left_split_btn.setObjectName("SidebarSplitToggle")
        self._left_split_btn.clicked.connect(self._toggle_split_left)
        self._left_sidebar.layout().addWidget(self._left_split_btn)

        self._right_split_btn = QPushButton("Split Sidebar")
        self._right_split_btn.setObjectName("SidebarSplitToggle")
        self._right_split_btn.clicked.connect(self._toggle_split_right)
        self._right_sidebar.layout().addWidget(self._right_split_btn)

        # Center area (GL preview + transport)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)

        self._gl_widget = GLPreviewWidget()
        center_layout.addWidget(self._gl_widget, stretch=1)

        self._transport = TransportBar()
        center_layout.addWidget(self._transport)

        # Main splitter: left_sidebar | center | right_sidebar
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._left_sidebar)
        self._splitter.addWidget(center)
        self._splitter.addWidget(self._right_sidebar)
        self._splitter.setStretchFactor(0, 0)  # left sidebar: don't stretch
        self._splitter.setStretchFactor(1, 1)  # center: take remaining space
        self._splitter.setStretchFactor(2, 0)  # right sidebar: don't stretch
        self._splitter.setSizes([430, 750, 430])

        # Assemble: left_strip | splitter | right_strip
        main_layout.addWidget(left_strip)
        main_layout.addWidget(self._splitter, stretch=1)
        main_layout.addWidget(right_strip)

        # Convenience aliases for backward-compatible access
        self._visual_panel = self._left_panels["visual"]
        self._text_panel = self._left_panels["text"]
        self._analysis_panel = self._left_panels["analysis"]
        self._preset_panel = self._left_panels["presets"]
        self._project_settings_panel = self._left_panels["export"]

        # Position update timer
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(50)  # 20 Hz
        self._position_timer.timeout.connect(self._update_position)

    def _toggle_left_sidebar(self) -> None:
        """Toggle left sidebar visibility."""
        visible = self._left_sidebar.isVisible()
        self._left_sidebar.setVisible(not visible)
        self._left_toggle_btn.setText("\u25B6" if visible else "\u25C0")

    def _toggle_right_sidebar(self) -> None:
        """Toggle right sidebar visibility."""
        visible = self._right_sidebar.isVisible()
        self._right_sidebar.setVisible(not visible)
        self._right_toggle_btn.setText("\u25C0" if visible else "\u25B6")

    def _toggle_split_left(self) -> None:
        self._left_sidebar.toggle_split()
        is_split = self._left_sidebar.is_split
        self._split_left_action.setChecked(is_split)
        self._left_split_btn.setText("Unsplit Sidebar" if is_split else "Split Sidebar")

    def _toggle_split_right(self) -> None:
        self._right_sidebar.toggle_split()
        is_split = self._right_sidebar.is_split
        self._split_right_action.setChecked(is_split)
        self._right_split_btn.setText("Unsplit Sidebar" if is_split else "Split Sidebar")

    def _connect_signals(self) -> None:
        # Connect all visual/text/analysis panels from both sidebars
        for panel in self._all_visual_panels():
            panel.params_changed.connect(self._on_params_changed)
            panel.preview_flags_changed.connect(self._on_preview_flags_changed)
        for panel in self._all_text_panels():
            panel.params_changed.connect(self._on_params_changed)
        for panel in self._all_analysis_panels():
            panel.params_changed.connect(self._on_params_changed)

        # Connect all preset panels
        for panel in self._all_preset_panels():
            panel.preset_selected.connect(self._on_preset_selected)

        # Connect export button in all export panels
        for panel in self._all_export_panels():
            panel.export_requested.connect(self._on_export_video)

        # Transport
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
        self._gl_widget.set_audio_duration(metadata.duration)

        # Auto-set overlay title from filename if empty
        preset = self._visual_panel._preset
        if preset is not None and not preset.overlay.title_text:
            preset.overlay.title_text = path.stem
            self._apply_preset(preset)

        # Pass source audio bitrate to export panels
        for panel in self._all_export_panels():
            panel.set_audio_metadata(metadata.bitrate)

        self.setWindowTitle(f"Wavern — {path.name}")
        logger.info("Loaded audio: %s (%.1fs)", path.name, metadata.duration)

        self._gl_widget.render_single_frame()

    def _apply_preset(self, preset: Preset) -> None:
        """Apply a preset to all components across both sidebars."""
        self._gl_widget.set_preset(preset)

        for panel in self._all_visual_panels():
            panel.set_preset(preset)
        for panel in self._all_text_panels():
            panel.set_preset(preset)
        for panel in self._all_analysis_panels():
            panel.set_preset(preset)
        for panel in self._all_preset_panels():
            panel.set_current_preset(preset)

        self._sync_format_to_background(preset.background.type)
        if not self._player.is_playing:
            self._gl_widget.render_single_frame()

    def _prompt_import_audio(self, context: str) -> bool:
        """Show 'no audio' dialog with an Import Audio button. Returns True if audio was loaded."""
        if getattr(self, "_import_dialog_open", False):
            return False
        self._import_dialog_open = True

        msg = QMessageBox(self)
        msg.setWindowTitle(context)
        msg.setText("Import an audio file first.")
        ok_btn = msg.addButton(QMessageBox.StandardButton.Ok)
        import_btn = msg.addButton("Import Audio", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(import_btn)
        msg.setEscapeButton(ok_btn)
        msg.exec()

        self._import_dialog_open = False
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

        preset = self._visual_panel._preset
        if preset is None:
            preset = DEFAULT_PRESET

        project_settings = self._project_settings_panel.settings
        dialog = ExportDialog(self._audio_path, preset, project_settings, self)
        dialog.exec()

    def _on_preset_selected(self, preset: Preset) -> None:
        self._apply_preset(preset)

    def _on_params_changed(self, preset: Preset) -> None:
        """Handle params_changed from any panel — sync to GL and all other panels."""
        sender = self.sender()

        self._gl_widget.update_preset(preset)
        self._sync_format_to_background(preset.background.type)

        # Sync all panel instances except the emitting one (in-place updates)
        for panel in self._all_visual_panels():
            if panel is not sender:
                panel.update_values(preset)

        for panel in self._all_text_panels():
            if panel is not sender:
                panel.update_values(preset)

        for panel in self._all_analysis_panels():
            if panel is not sender:
                panel.update_values(preset)

        for panel in self._all_preset_panels():
            panel.set_current_preset(preset)

        if not self._player.is_playing:
            self._gl_widget.render_single_frame()

    def _on_preview_flags_changed(self, skip_bg: bool, skip_overlay: bool) -> None:
        """Update renderer preview-skip flags from visual panel toggles."""
        self._gl_widget.set_preview_flags(skip_bg, skip_overlay)
        if not self._player.is_playing:
            self._gl_widget.render_single_frame()

    def _sync_format_to_background(self, bg_type: str) -> None:
        """Restrict format options when background is transparent.

        When bg is "none", non-alpha formats (mp4, gif) are disabled in the
        sidebar. If the current format is incompatible, it auto-switches to
        webm. When bg changes back, all formats are re-enabled.
        """
        if bg_type == self._bg_type:
            return
        self._bg_type = bg_type
        is_alpha = bg_type == "none"
        for panel in self._all_export_panels():
            panel.set_alpha_mode(is_alpha)

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
        if not self._player.is_playing:
            self._gl_widget.render_single_frame()

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

        key = event.key()
        mods = event.modifiers()

        focused = QApplication.focusWidget()
        input_focused = isinstance(focused, (QAbstractSpinBox, QLineEdit))

        # Space → play/pause, but not when a text field has focus (user may be typing)
        if key == Qt.Key.Key_Space:
            if isinstance(focused, QLineEdit):
                return super().eventFilter(obj, event)
            self._transport._on_play_clicked()
            return True

        if input_focused:
            return super().eventFilter(obj, event)

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

        # M → mute / unmute
        if key == Qt.Key.Key_M:
            self._player.muted = not self._player.muted
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Up → volume +5% (unmutes if muted)
        if key == Qt.Key.Key_Up:
            self._player.muted = False
            self._player.volume = self._player.volume + 0.05
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Down → volume -5% (unmutes if muted)
        if key == Qt.Key.Key_Down:
            self._player.muted = False
            self._player.volume = self._player.volume - 0.05
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # F → toggle fullscreen (same as F11)
        if key == Qt.Key.Key_F:
            self._on_toggle_fullscreen()
            return True

        # 0–9 → seek to 0%, 10%, 20%, … 90% of duration
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9 and not mods:
            duration = self._player.duration
            if duration > 0:
                fraction = (key - Qt.Key.Key_0) / 10.0
                pos = duration * fraction
                self._on_seek(pos)
                self._transport.update_position(pos)
            return True

        return super().eventFilter(obj, event)

    def _on_save_preset_as(self) -> None:
        """Delegate to the preset panel's save flow."""
        self._preset_panel._on_save()

    def _on_toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and the previous window state."""
        if self.isFullScreen():
            target = Qt.WindowState.WindowMaximized if self._was_maximized else Qt.WindowState.WindowNoState
            self.setWindowState(target)
        else:
            self._was_maximized = self.isMaximized()
            self.setWindowState(Qt.WindowState.WindowFullScreen)

    def _on_theme_selected(self) -> None:
        """Apply the selected theme and save the preference."""
        action = self.sender()
        if action is None:
            return
        theme_name = action.data()
        app = QApplication.instance()
        if app is not None:
            self._theme_manager.apply(app, theme_name)
            self._theme_manager.save_preference(theme_name)

    def _on_viz_shortcut(self) -> None:
        """Switch visualization type via Ctrl+1…N (one per registered visualization)."""
        action = self.sender()
        if action is None:
            return
        index = action.data()
        self._visual_panel.set_viz_by_index(index)

    def closeEvent(self, event) -> None:
        """Cleanup on window close."""
        QApplication.instance().removeEventFilter(self)
        self._player.stop()
        self._gl_widget.stop_preview()
        self._gl_widget.cleanup()
        super().closeEvent(event)

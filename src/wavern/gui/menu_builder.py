"""Menu bar construction for the main application window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from wavern.gui.theme_manager import ThemeManager
from wavern.visualizations.registry import VisualizationRegistry

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow


def build_menu_bar(
    window: QMainWindow,
    theme_manager: ThemeManager,
    *,
    on_import: callable,  # type: ignore[reportGeneralTypeIssues]
    on_export: callable,  # type: ignore[reportGeneralTypeIssues]
    on_save_preset: callable,  # type: ignore[reportGeneralTypeIssues]
    on_toggle_left: callable,  # type: ignore[reportGeneralTypeIssues]
    on_toggle_right: callable,  # type: ignore[reportGeneralTypeIssues]
    on_split_left: callable,  # type: ignore[reportGeneralTypeIssues]
    on_split_right: callable,  # type: ignore[reportGeneralTypeIssues]
    on_fullscreen: callable,  # type: ignore[reportGeneralTypeIssues]
    on_ambient: callable,  # type: ignore[reportGeneralTypeIssues]
    on_theme_selected: callable,  # type: ignore[reportGeneralTypeIssues]
    on_viz_shortcut: callable,  # type: ignore[reportGeneralTypeIssues]
) -> dict[str, QAction]:
    """Build the application menu bar and return named action references.

    Args:
        window: The main window to attach the menu bar to.
        theme_manager: Used to list available themes and read the current one.
        on_import: Callback for import audio action.
        on_export: Callback for export video action.
        on_save_preset: Callback for save preset action.
        on_toggle_left: Callback for toggle left sidebar.
        on_toggle_right: Callback for toggle right sidebar.
        on_split_left: Callback for split left sidebar.
        on_split_right: Callback for split right sidebar.
        on_fullscreen: Callback for fullscreen toggle.
        on_ambient: Callback for ambient mode toggle.
        on_theme_selected: Callback for theme selection.
        on_viz_shortcut: Callback for visualization shortcuts.

    Returns:
        Dict of named QAction references the caller may need later.
    """
    window.menuBar().setNativeMenuBar(False)
    menubar = window.menuBar()

    actions: dict[str, QAction] = {}

    # --- File menu ---
    file_menu = menubar.addMenu("File")

    import_action = QAction("Import Audio...", window)
    import_action.setShortcut("Ctrl+O")
    import_action.triggered.connect(on_import)
    file_menu.addAction(import_action)

    export_action = QAction("Render Video...", window)
    export_action.setShortcut("Ctrl+E")
    export_action.triggered.connect(on_export)
    file_menu.addAction(export_action)

    file_menu.addSeparator()

    quit_action = QAction("Quit", window)
    quit_action.setShortcut("Ctrl+Q")
    quit_action.triggered.connect(window.close)
    file_menu.addAction(quit_action)

    file_menu.addSeparator()

    save_preset_action = QAction("Save Preset As\u2026", window)
    save_preset_action.setShortcut("Ctrl+S")
    save_preset_action.triggered.connect(on_save_preset)
    file_menu.addAction(save_preset_action)

    # --- View menu ---
    view_menu = menubar.addMenu("View")

    toggle_left = QAction("Toggle Left Sidebar", window)
    toggle_left.setShortcut("Ctrl+B")
    toggle_left.triggered.connect(on_toggle_left)
    view_menu.addAction(toggle_left)
    actions["toggle_left"] = toggle_left

    toggle_right = QAction("Toggle Right Sidebar", window)
    toggle_right.setShortcut(QKeySequence("Ctrl+Shift+B"))
    toggle_right.triggered.connect(on_toggle_right)
    view_menu.addAction(toggle_right)
    actions["toggle_right"] = toggle_right

    view_menu.addSeparator()

    split_left = QAction("Split Left Sidebar", window)
    split_left.setCheckable(True)
    split_left.triggered.connect(on_split_left)
    view_menu.addAction(split_left)
    actions["split_left"] = split_left

    split_right = QAction("Split Right Sidebar", window)
    split_right.setCheckable(True)
    split_right.triggered.connect(on_split_right)
    view_menu.addAction(split_right)
    actions["split_right"] = split_right

    view_menu.addSeparator()

    fullscreen_action = QAction("Fullscreen Preview", window)
    fullscreen_action.setShortcut("F11")
    fullscreen_action.triggered.connect(on_fullscreen)
    view_menu.addAction(fullscreen_action)

    ambient_action = QAction("Ambient Mode", window)
    ambient_action.setShortcut("Ctrl+H")
    ambient_action.setCheckable(True)
    ambient_action.triggered.connect(on_ambient)
    view_menu.addAction(ambient_action)
    actions["ambient_mode"] = ambient_action

    view_menu.addSeparator()

    # Theme submenu
    theme_menu = view_menu.addMenu("Theme")
    theme_group = QActionGroup(window)
    theme_group.setExclusive(True)
    current_theme = theme_manager.load_preference()
    for theme_name in theme_manager.list_themes():
        action = QAction(theme_name.capitalize(), window)
        action.setCheckable(True)
        action.setData(theme_name)
        if theme_name == current_theme:
            action.setChecked(True)
        action.triggered.connect(on_theme_selected)
        theme_group.addAction(action)
        theme_menu.addAction(action)

    # --- Visualization shortcuts (Ctrl+1…N) ---
    viz_menu = menubar.addMenu("Visualization")
    import wavern.visualizations  # noqa: F401 — triggers @register decorators

    viz_infos = VisualizationRegistry().list_all()
    for i, info in enumerate(viz_infos, start=1):
        shortcut_key = None
        if i <= 9:
            shortcut_key = f"Ctrl+{i}"
        elif i == 10:
            shortcut_key = "Ctrl+0"

        label = f"Switch to {info['display_name']}"
        if shortcut_key:
            label += f" ({shortcut_key})"
        action = QAction(label, window)
        if shortcut_key:
            action.setShortcut(shortcut_key)
        action.setData(i - 1)
        action.triggered.connect(on_viz_shortcut)
        viz_menu.addAction(action)

    return actions

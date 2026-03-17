"""Theme manager — loads QSS stylesheets and persists user preference."""

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_THEMES_DIR = Path(__file__).parent / "themes"
_DEFAULT_THEME = "dark"


class ThemeManager:
    """Manages application themes (QSS stylesheets) and persists the user's choice."""

    def __init__(self) -> None:
        self._settings = QSettings("wavern", "wavern")
        self._cache: dict[str, str] = {}
        self._current_theme: str | None = None
        self._preload_themes()

    def _preload_themes(self) -> None:
        """Pre-load all QSS files into memory to avoid disk I/O during theme switches."""
        if not _THEMES_DIR.is_dir():
            return
        for qss_path in _THEMES_DIR.glob("*.qss"):
            try:
                self._cache[qss_path.stem] = qss_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Failed to preload theme: %s", qss_path)

    def list_themes(self) -> list[str]:
        """Return sorted list of available theme names (without .qss extension)."""
        if not _THEMES_DIR.is_dir():
            return [_DEFAULT_THEME]
        return sorted(p.stem for p in _THEMES_DIR.glob("*.qss"))

    def apply(self, app: QApplication, theme_name: str) -> None:
        """Load and apply a QSS theme to the application.

        Skips re-applying if the requested theme is already active. Shows a
        wait cursor during the stylesheet switch, since Qt must synchronously
        re-polish every widget in the application tree.
        """
        if theme_name == self._current_theme:
            return

        stylesheet = self._cache.get(theme_name)
        if stylesheet is None:
            # Fallback: try reading from disk (e.g. theme added after startup)
            qss_path = _THEMES_DIR / f"{theme_name}.qss"
            if not qss_path.exists():
                logger.warning("Theme file not found: %s", qss_path)
                return
            stylesheet = qss_path.read_text(encoding="utf-8")
            self._cache[theme_name] = stylesheet

        app.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            app.setStyleSheet(stylesheet)
            self._current_theme = theme_name
            logger.info("Applied theme: %s", theme_name)
        finally:
            app.restoreOverrideCursor()

    def save_preference(self, name: str) -> None:
        """Persist the user's theme choice."""
        self._settings.setValue("theme", name)

    def load_preference(self) -> str:
        """Load the saved theme preference, defaulting to 'dark'."""
        return str(self._settings.value("theme", _DEFAULT_THEME))

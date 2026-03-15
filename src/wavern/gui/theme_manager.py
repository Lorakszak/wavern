"""Theme manager — loads QSS stylesheets and persists user preference."""

import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_THEMES_DIR = Path(__file__).parent / "themes"
_DEFAULT_THEME = "dark"


class ThemeManager:
    """Manages application themes (QSS stylesheets) and persists the user's choice."""

    def __init__(self) -> None:
        self._settings = QSettings("wavern", "wavern")

    def list_themes(self) -> list[str]:
        """Return sorted list of available theme names (without .qss extension)."""
        if not _THEMES_DIR.is_dir():
            return [_DEFAULT_THEME]
        return sorted(p.stem for p in _THEMES_DIR.glob("*.qss"))

    def apply(self, app: QApplication, theme_name: str) -> None:
        """Load and apply a QSS theme to the application."""
        qss_path = _THEMES_DIR / f"{theme_name}.qss"
        if not qss_path.exists():
            logger.warning("Theme file not found: %s", qss_path)
            return
        stylesheet = qss_path.read_text(encoding="utf-8")
        app.setStyleSheet(stylesheet)
        logger.info("Applied theme: %s", theme_name)

    def save_preference(self, name: str) -> None:
        """Persist the user's theme choice."""
        self._settings.setValue("theme", name)

    def load_preference(self) -> str:
        """Load the saved theme preference, defaulting to 'dark'."""
        return str(self._settings.value("theme", _DEFAULT_THEME))

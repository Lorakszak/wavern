"""Persistent storage for favorite presets — a UI preference, not preset data."""

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from wavern.config import get_favorites_path

logger = logging.getLogger(__name__)


class FavoritesStore(QObject):
    """Manages a set of favorited preset names, persisted as JSON.

    File location: ``~/.config/wavern/favorites.json``
    (respects ``XDG_CONFIG_HOME``).
    """

    changed = Signal()

    def __init__(self, config_dir: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        favorites_path = get_favorites_path() if config_dir is None else config_dir / "favorites.json"
        self._config_dir = favorites_path.parent
        self._path = favorites_path
        self._favorites: set[str] = self._load()

    def is_favorite(self, name: str) -> bool:
        """Check if a preset name is marked as a favorite."""
        return name in self._favorites

    def toggle(self, name: str) -> None:
        """Add or remove a preset name from favorites, persist, and emit ``changed``."""
        if name in self._favorites:
            self._favorites.discard(name)
            logger.debug("Favorite removed: %s", name)
        else:
            self._favorites.add(name)
            logger.debug("Favorite added: %s", name)
        self._save()
        self.changed.emit()

    def all_favorites(self) -> set[str]:
        """Return a copy of the current favorites set."""
        return set(self._favorites)

    def _load(self) -> set[str]:
        """Load favorites from disk. Returns empty set on any error."""
        if not self._path.exists():
            return set()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            items = data.get("favorites", [])
            if isinstance(items, list):
                return {str(item) for item in items}
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning("Could not load favorites from %s: %s", self._path, e)
        return set()

    def _save(self) -> None:
        """Persist the current favorites set to disk (atomic write)."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        payload = {"favorites": sorted(self._favorites)}
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.rename(self._path)

"""Tests for wavern.gui.favorites_store.

WHAT THIS TESTS:
- toggle() adds and removes preset names from the favorites set
- Favorites persist across FavoritesStore instances using the same config directory
- Corrupt or missing favorites.json files are handled gracefully
- changed signal is emitted on every toggle call
- Favorites JSON is written as a sorted list under the "favorites" key
Does NOT test: preset panel UI integration or preset loading
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wavern.gui.favorites_store import FavoritesStore


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Temporary config directory for test isolation."""
    d = tmp_path / "wavern_cfg"
    d.mkdir()
    return d


class TestFavoritesStore:
    """FavoritesStore unit tests."""

    def test_toggle_adds_and_removes(self, config_dir: Path) -> None:
        store = FavoritesStore(config_dir=config_dir)
        assert not store.is_favorite("My Preset")

        store.toggle("My Preset")
        assert store.is_favorite("My Preset")

        store.toggle("My Preset")
        assert not store.is_favorite("My Preset")

    def test_all_favorites_returns_copy(self, config_dir: Path) -> None:
        store = FavoritesStore(config_dir=config_dir)
        store.toggle("A")
        store.toggle("B")
        favs = store.all_favorites()
        assert favs == {"A", "B"}
        # Mutating returned set does not affect store
        favs.add("C")
        assert not store.is_favorite("C")

    def test_persistence_across_instances(self, config_dir: Path) -> None:
        store1 = FavoritesStore(config_dir=config_dir)
        store1.toggle("Persistent")
        assert store1.is_favorite("Persistent")

        # New instance reads same file
        store2 = FavoritesStore(config_dir=config_dir)
        assert store2.is_favorite("Persistent")

    def test_corrupt_file_graceful_fallback(self, config_dir: Path) -> None:
        fav_path = config_dir / "favorites.json"
        fav_path.write_text("NOT VALID JSON!!!", encoding="utf-8")

        store = FavoritesStore(config_dir=config_dir)
        assert store.all_favorites() == set()
        # Should still work after corrupt load
        store.toggle("Recovery")
        assert store.is_favorite("Recovery")

    def test_missing_file_starts_empty(self, config_dir: Path) -> None:
        store = FavoritesStore(config_dir=config_dir)
        assert store.all_favorites() == set()

    def test_changed_signal_emitted_on_toggle(self, config_dir: Path) -> None:
        store = FavoritesStore(config_dir=config_dir)
        callback = MagicMock()
        store.changed.connect(callback)

        store.toggle("X")
        assert callback.call_count == 1

        store.toggle("X")
        assert callback.call_count == 2

    def test_favorites_json_structure(self, config_dir: Path) -> None:
        store = FavoritesStore(config_dir=config_dir)
        store.toggle("B Preset")
        store.toggle("A Preset")

        data = json.loads((config_dir / "favorites.json").read_text(encoding="utf-8"))
        assert "favorites" in data
        assert data["favorites"] == ["A Preset", "B Preset"]  # sorted

    def test_config_dir_created_on_save(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "config"
        store = FavoritesStore(config_dir=nested)
        store.toggle("Auto-mkdir")
        assert (nested / "favorites.json").exists()

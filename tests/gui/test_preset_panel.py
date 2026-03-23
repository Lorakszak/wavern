"""Tests for wavern.gui.preset_panel — viz type filter.

WHAT THIS TESTS:
- Viz type combo is populated with "All Types" + one item per registered visualization
- Selecting a viz type filters the preset list to matching presets only
- Selecting "All Types" shows all presets regardless of visualization_type
Does NOT test: save/delete/rename operations, favorites, or source filter (covered elsewhere)
"""

from unittest.mock import MagicMock, patch

import pytest

from wavern.gui.favorites_store import FavoritesStore
from wavern.gui.preset_panel import PresetPanel
from wavern.presets.manager import PresetManager


def _make_panel(tmp_path, preset_entries_with_type):
    """Build a PresetPanel backed by mocked manager and favorites."""
    manager = MagicMock(spec=PresetManager)
    manager.list_presets_with_type.return_value = preset_entries_with_type
    manager.list_presets.return_value = [
        {k: v for k, v in e.items() if k != "visualization_type"}
        for e in preset_entries_with_type
    ]

    favorites = FavoritesStore(config_dir=tmp_path / "cfg")
    panel = PresetPanel(preset_manager=manager, favorites_store=favorites)
    return panel


class TestVizTypeFilterCombo:
    def test_combo_has_all_types_as_first_item(self, tmp_path):
        panel = _make_panel(tmp_path, [])
        assert panel._viz_combo.itemText(0) == "All Types"
        assert panel._viz_combo.itemData(0) == ""

    def test_combo_populated_with_registered_vizs(self, tmp_path):
        from wavern.visualizations.registry import VisualizationRegistry

        registry = VisualizationRegistry()
        registered = registry.list_all()
        panel = _make_panel(tmp_path, [])

        # combo count = 1 (All Types) + number of registered vizs
        assert panel._viz_combo.count() == 1 + len(registered)

    def test_combo_data_values_are_viz_names(self, tmp_path):
        from wavern.visualizations.registry import VisualizationRegistry

        registry = VisualizationRegistry()
        names = {v["name"] for v in registry.list_all()}
        panel = _make_panel(tmp_path, [])

        data_values = {
            panel._viz_combo.itemData(i)
            for i in range(1, panel._viz_combo.count())
        }
        assert data_values == names


class TestVizTypeFilterBehavior:
    _entries = [
        {"name": "Spectrum A", "source": "builtin", "path": "/a.json", "visualization_type": "spectrum_bars"},
        {"name": "Spectrum B", "source": "builtin", "path": "/b.json", "visualization_type": "spectrum_bars"},
        {"name": "Wave C", "source": "builtin", "path": "/c.json", "visualization_type": "waveform"},
    ]

    def _visible_names(self, panel) -> list[str]:
        return [
            panel._preset_list.item(i).data(0x0100)  # Qt.ItemDataRole.UserRole
            for i in range(panel._preset_list.count())
        ]

    def test_all_types_shows_all_presets(self, tmp_path):
        panel = _make_panel(tmp_path, self._entries)
        panel._viz_combo.setCurrentIndex(0)  # "All Types"
        names = self._visible_names(panel)
        assert set(names) == {"Spectrum A", "Spectrum B", "Wave C"}

    def test_viz_filter_narrows_to_matching_type(self, tmp_path):
        panel = _make_panel(tmp_path, self._entries)

        # Find and select "spectrum_bars" in combo
        idx = panel._viz_combo.findData("spectrum_bars")
        assert idx >= 0
        panel._viz_combo.setCurrentIndex(idx)

        names = self._visible_names(panel)
        assert set(names) == {"Spectrum A", "Spectrum B"}
        assert "Wave C" not in names

    def test_viz_filter_combined_with_source_filter(self, tmp_path):
        entries = [
            {"name": "Builtin Spec", "source": "builtin", "path": "/a.json", "visualization_type": "spectrum_bars"},
            {"name": "User Spec", "source": "user", "path": "/b.json", "visualization_type": "spectrum_bars"},
            {"name": "User Wave", "source": "user", "path": "/c.json", "visualization_type": "waveform"},
        ]
        panel = _make_panel(tmp_path, entries)

        # Apply viz filter
        idx = panel._viz_combo.findData("spectrum_bars")
        panel._viz_combo.setCurrentIndex(idx)

        # Apply source filter: User only
        panel._source_combo.setCurrentText("User")

        names = self._visible_names(panel)
        assert names == ["User Spec"]

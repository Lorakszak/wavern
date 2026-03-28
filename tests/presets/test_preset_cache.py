"""Tests for PresetManager metadata cache.

WHAT THIS TESTS:
- list_presets_with_type() caches results after first call
- save() invalidates the cache so next call re-reads disk
- delete() invalidates the cache
Does NOT test: preset loading, schema validation
"""

import pytest

from wavern.presets.manager import PresetManager
from wavern.presets.schema import Preset, VisualizationLayer


@pytest.fixture
def tmp_preset_dir(tmp_path):
    return tmp_path / "presets"


@pytest.fixture
def manager(tmp_preset_dir):
    return PresetManager(user_preset_dir=tmp_preset_dir)


@pytest.fixture
def sample_preset():
    return Preset(
        name="Cache Test",
        layers=[VisualizationLayer(visualization_type="spectrum_bars")],
    )


class TestPresetMetadataCache:
    def test_second_call_returns_cached(self, manager, sample_preset):
        manager.save(sample_preset)
        first = manager.list_presets_with_type()
        second = manager.list_presets_with_type()
        assert first is second

    def test_save_invalidates_cache(self, manager, sample_preset):
        manager.save(sample_preset)
        first = manager.list_presets_with_type()

        new_preset = Preset(
            name="Another",
            layers=[VisualizationLayer(visualization_type="particles")],
        )
        manager.save(new_preset)
        second = manager.list_presets_with_type()

        assert first is not second
        names = [p["name"] for p in second]
        assert "Another" in names

    def test_delete_invalidates_cache(self, manager, sample_preset):
        manager.save(sample_preset)
        first = manager.list_presets_with_type()
        manager.delete("Cache Test")
        second = manager.list_presets_with_type()
        assert first is not second

    def test_list_presets_uses_cache(self, manager, sample_preset):
        manager.save(sample_preset)
        _ = manager.list_presets_with_type()
        presets = manager.list_presets()
        assert any(p["name"] == "Cache Test" for p in presets)

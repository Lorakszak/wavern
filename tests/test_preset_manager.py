"""Tests for PresetManager."""

import json
from pathlib import Path

import pytest

from wavern.presets.manager import PresetError, PresetManager
from wavern.presets.schema import Preset, VisualizationParams


@pytest.fixture
def tmp_preset_dir(tmp_path):
    """Create a temporary preset directory."""
    return tmp_path / "presets"


@pytest.fixture
def manager(tmp_preset_dir):
    """Create a PresetManager with a temp directory."""
    return PresetManager(user_preset_dir=tmp_preset_dir)


@pytest.fixture
def sample_preset():
    return Preset(
        name="Test Preset",
        visualization=VisualizationParams(
            visualization_type="spectrum_bars",
            params={"bar_count": 32},
        ),
    )


class TestPresetManager:
    def test_save_and_load(self, manager, sample_preset):
        path = manager.save(sample_preset)
        assert path.exists()

        loaded = manager.load("Test Preset")
        assert loaded.name == "Test Preset"
        assert loaded.visualization.params["bar_count"] == 32

    def test_list_presets(self, manager, sample_preset):
        manager.save(sample_preset)
        presets = manager.list_presets()

        user_presets = [p for p in presets if p["source"] == "user"]
        assert any(p["name"] == "Test Preset" for p in user_presets)

    def test_delete(self, manager, sample_preset):
        manager.save(sample_preset)
        manager.delete("Test Preset")

        with pytest.raises(PresetError):
            manager.load("Test Preset")

    def test_delete_nonexistent(self, manager):
        with pytest.raises(PresetError):
            manager.delete("Does Not Exist")

    def test_load_nonexistent(self, manager):
        with pytest.raises(PresetError):
            manager.load("Does Not Exist")

    def test_load_from_path(self, manager, sample_preset, tmp_path):
        file_path = tmp_path / "custom.json"
        file_path.write_text(sample_preset.model_dump_json(), encoding="utf-8")

        loaded = manager.load_from_path(file_path)
        assert loaded.name == "Test Preset"

    def test_export_import(self, manager, sample_preset, tmp_path):
        manager.save(sample_preset)

        export_path = tmp_path / "exported.json"
        manager.export_preset("Test Preset", export_path)
        assert export_path.exists()

        # Import to a new manager
        manager2 = PresetManager(user_preset_dir=tmp_path / "presets2")
        imported = manager2.import_preset(export_path)
        assert imported.name == "Test Preset"

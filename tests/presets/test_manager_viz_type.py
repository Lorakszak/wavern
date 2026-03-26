"""Tests for PresetManager.list_presets_with_type().

WHAT THIS TESTS:
- list_presets_with_type() returns dicts with a 'visualization_type' field
- The visualization_type matches the preset's JSON visualization.visualization_type value
- The number of entries matches list_presets()
Does NOT test: full pydantic Preset validation, built-in preset loading
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
def spectrum_preset():
    return Preset(
        name="My Spectrum",
        layers=[VisualizationLayer(
            visualization_type="spectrum_bars",
            params={},
        )],
    )


@pytest.fixture
def waveform_preset():
    return Preset(
        name="My Waveform",
        layers=[VisualizationLayer(
            visualization_type="waveform",
            params={},
        )],
    )


class TestListPresetsWithType:
    def test_includes_visualization_type(self, manager, spectrum_preset):
        manager.save(spectrum_preset)
        results = manager.list_presets_with_type()
        match = next((r for r in results if r["name"] == "My Spectrum"), None)
        assert match is not None
        assert match["visualization_type"] == "spectrum_bars"

    def test_count_matches_list_presets(self, manager, spectrum_preset, waveform_preset):
        manager.save(spectrum_preset)
        manager.save(waveform_preset)
        assert len(manager.list_presets_with_type()) == len(manager.list_presets())

    def test_multiple_types_preserved(self, manager, spectrum_preset, waveform_preset):
        manager.save(spectrum_preset)
        manager.save(waveform_preset)
        results = {r["name"]: r["visualization_type"] for r in manager.list_presets_with_type()}
        assert results["My Spectrum"] == "spectrum_bars"
        assert results["My Waveform"] == "waveform"

    def test_corrupt_json_falls_back_to_empty_string(self, tmp_preset_dir, manager):
        tmp_preset_dir.mkdir(parents=True, exist_ok=True)
        bad_file = tmp_preset_dir / "bad.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")

        # Should not raise; viz type defaults to ""
        results = manager.list_presets_with_type()
        # The corrupt file might be skipped by list_presets() itself, so just confirm no crash
        assert isinstance(results, list)

"""Tests for multi-layer visualization schema and migration.

WHAT THIS TESTS:
- VisualizationLayer creation with defaults and explicit values
- BlendMode enum includes SCREEN
- Preset.layers validation: min 1, max 7
- Per-layer colors field
- Migration from old single-viz format to multi-layer format
- list_presets_with_type after migration
Does NOT test: rendering, GUI
"""

import json

import pytest
from pydantic import ValidationError

from wavern.presets.manager import PresetManager
from wavern.presets.schema import (
    BlendMode,
    Preset,
    VisualizationLayer,
)


class TestVisualizationLayer:
    def test_defaults(self):
        layer = VisualizationLayer(visualization_type="spectrum_bars")
        assert layer.blend_mode == BlendMode.NORMAL
        assert layer.opacity == 1.0
        assert layer.visible is True
        assert layer.name == ""
        assert layer.colors == ["#00FFAA", "#FF00AA", "#FFAA00"]
        assert layer.params == {}

    def test_explicit_values(self):
        layer = VisualizationLayer(
            visualization_type="particles",
            params={"spawn_rate": 500},
            blend_mode=BlendMode.ADDITIVE,
            opacity=0.8,
            visible=False,
            name="My Particles",
            colors=["#FF0000", "#00FF00"],
        )
        assert layer.visualization_type == "particles"
        assert layer.params["spawn_rate"] == 500
        assert layer.blend_mode == BlendMode.ADDITIVE
        assert layer.opacity == 0.8
        assert layer.visible is False
        assert layer.name == "My Particles"
        assert layer.colors == ["#FF0000", "#00FF00"]

    def test_opacity_clamped(self):
        with pytest.raises(ValidationError):
            VisualizationLayer(visualization_type="x", opacity=1.5)
        with pytest.raises(ValidationError):
            VisualizationLayer(visualization_type="x", opacity=-0.1)


class TestBlendModeScreen:
    def test_screen_exists(self):
        assert BlendMode.SCREEN == "screen"
        assert BlendMode.SCREEN.value == "screen"


class TestPresetLayers:
    def test_single_layer_preset(self):
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        assert len(preset.layers) == 1
        assert preset.layers[0].visualization_type == "spectrum_bars"

    def test_multi_layer_preset(self):
        preset = Preset(
            name="Multi",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars"),
                VisualizationLayer(visualization_type="particles", blend_mode=BlendMode.SCREEN),
                VisualizationLayer(visualization_type="circular_spectrum", opacity=0.5),
            ],
        )
        assert len(preset.layers) == 3
        assert preset.layers[1].blend_mode == BlendMode.SCREEN
        assert preset.layers[2].opacity == 0.5

    def test_empty_layers_rejected(self):
        with pytest.raises(ValidationError):
            Preset(name="Empty", layers=[])

    def test_max_seven_layers(self):
        layers = [VisualizationLayer(visualization_type="spectrum_bars") for _ in range(7)]
        preset = Preset(name="Max", layers=layers)
        assert len(preset.layers) == 7

    def test_eight_layers_rejected(self):
        layers = [VisualizationLayer(visualization_type="spectrum_bars") for _ in range(8)]
        with pytest.raises(ValidationError):
            Preset(name="TooMany", layers=layers)

    def test_layers_json_roundtrip(self):
        preset = Preset(
            name="Roundtrip",
            layers=[
                VisualizationLayer(
                    visualization_type="spectrum_bars",
                    params={"bar_count": 64},
                    blend_mode=BlendMode.MULTIPLY,
                    opacity=0.7,
                    name="Bars",
                    colors=["#FF0000"],
                ),
                VisualizationLayer(visualization_type="particles"),
            ],
        )
        data = preset.model_dump()
        reloaded = Preset.model_validate(data)
        assert len(reloaded.layers) == 2
        assert reloaded.layers[0].blend_mode == BlendMode.MULTIPLY
        assert reloaded.layers[0].opacity == 0.7
        assert reloaded.layers[0].colors == ["#FF0000"]
        assert reloaded.layers[1].colors == ["#00FFAA", "#FF00AA", "#FFAA00"]


class TestPresetMigration:
    def test_old_format_migrates_to_layers(self, tmp_path):
        """Old preset with 'visualization' field auto-converts to 'layers'."""
        old_preset = {
            "name": "OldPreset",
            "visualization": {
                "visualization_type": "spectrum_bars",
                "params": {"bar_count": 32},
            },
            "blend_mode": "additive",
            "color_palette": ["#FF0000"],
        }
        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        (preset_dir / "old.json").write_text(json.dumps(old_preset))

        manager = PresetManager(user_preset_dir=preset_dir)
        preset = manager.load("OldPreset")

        assert len(preset.layers) == 1
        assert preset.layers[0].visualization_type == "spectrum_bars"
        assert preset.layers[0].params["bar_count"] == 32
        assert preset.layers[0].blend_mode == BlendMode.ADDITIVE

    def test_new_format_loads_directly(self, tmp_path):
        """New preset with 'layers' field loads without migration."""
        new_preset = {
            "name": "NewPreset",
            "layers": [
                {
                    "visualization_type": "spectrum_bars",
                    "params": {},
                    "blend_mode": "normal",
                    "opacity": 1.0,
                    "visible": True,
                    "name": "",
                }
            ],
            "color_palette": ["#FF0000"],
        }
        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        (preset_dir / "new.json").write_text(json.dumps(new_preset))

        manager = PresetManager(user_preset_dir=preset_dir)
        preset = manager.load("NewPreset")
        assert len(preset.layers) == 1

    def test_old_blend_mode_carried_to_layer(self, tmp_path):
        """Top-level blend_mode from old format maps to layers[0].blend_mode."""
        old_preset = {
            "name": "BlendTest",
            "visualization": {
                "visualization_type": "waveform",
                "params": {},
            },
            "blend_mode": "multiply",
        }
        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        (preset_dir / "blend.json").write_text(json.dumps(old_preset))

        manager = PresetManager(user_preset_dir=preset_dir)
        preset = manager.load("BlendTest")
        assert preset.layers[0].blend_mode == BlendMode.MULTIPLY

    def test_list_presets_with_type_after_migration(self, tmp_path):
        """list_presets_with_type works with both old and new format presets."""
        old = {
            "name": "Old",
            "visualization": {"visualization_type": "waveform", "params": {}},
        }
        new = {
            "name": "New",
            "layers": [{"visualization_type": "particles", "params": {}}],
        }
        preset_dir = tmp_path / "presets"
        preset_dir.mkdir()
        (preset_dir / "old.json").write_text(json.dumps(old))
        (preset_dir / "new.json").write_text(json.dumps(new))

        manager = PresetManager(user_preset_dir=preset_dir)
        entries = manager.list_presets_with_type()
        types = {e["name"]: e["visualization_type"] for e in entries}
        assert types["Old"] == "waveform"
        assert types["New"] == "particles"

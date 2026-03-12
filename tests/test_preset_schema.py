"""Tests for preset schema validation."""


import pytest
from pydantic import ValidationError

from wavern.presets.schema import (
    BackgroundConfig,
    BlendMode,
    ColorStop,
    Preset,
    VisualizationParams,
)


class TestPresetSchema:
    def test_minimal_preset(self):
        preset = Preset(
            name="Test",
            visualization=VisualizationParams(
                visualization_type="spectrum_bars",
            ),
        )
        assert preset.name == "Test"
        assert preset.fps == 60
        assert preset.fft_size == 2048

    def test_full_preset(self):
        preset = Preset(
            name="Full Test",
            description="A complete preset",
            author="tester",
            visualization=VisualizationParams(
                visualization_type="waveform",
                params={"line_thickness": 3.0},
            ),
            color_palette=["#FF0000", "#00FF00"],
            blend_mode=BlendMode.ADDITIVE,
            background=BackgroundConfig(type="solid", color="#111111"),
            fft_size=4096,
            smoothing=0.5,
            fps=30,
        )
        assert preset.author == "tester"
        assert preset.visualization.params["line_thickness"] == 3.0

    def test_json_roundtrip(self):
        preset = Preset(
            name="Roundtrip",
            visualization=VisualizationParams(
                visualization_type="particles",
                params={"max_particles": 5000},
            ),
        )
        json_str = preset.model_dump_json()
        loaded = Preset.model_validate_json(json_str)
        assert loaded.name == "Roundtrip"
        assert loaded.visualization.params["max_particles"] == 5000

    def test_invalid_name_empty(self):
        with pytest.raises(ValidationError):
            Preset(
                name="",
                visualization=VisualizationParams(visualization_type="waveform"),
            )

    def test_invalid_fft_size(self):
        with pytest.raises(ValidationError):
            Preset(
                name="Bad FFT",
                visualization=VisualizationParams(visualization_type="waveform"),
                fft_size=100,  # below minimum 256
            )

    def test_color_stop_validation(self):
        stop = ColorStop(position=0.5, color="#FF00AA")
        assert stop.position == 0.5

        with pytest.raises(ValidationError):
            ColorStop(position=1.5, color="#FF00AA")

    def test_background_config_defaults(self):
        bg = BackgroundConfig()
        assert bg.type == "solid"
        assert bg.color == "#000000"
        assert bg.opacity == 1.0

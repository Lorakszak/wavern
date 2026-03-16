"""Tests for wavern.presets.schema.

WHAT THIS TESTS:
- Preset constructs with minimal and full field sets; JSON round-trip preserves all values
- ValidationError raised for empty name and out-of-range fft_size
- BackgroundConfig, ColorStop, VideoOverlayConfig field defaults and validation
- Preset round-trip including BackgroundMovement, transform fields, and VideoOverlayConfig
Does NOT test: preset file I/O or the PresetManager (see test_preset_manager)
"""


import pytest
from pydantic import ValidationError

from wavern.presets.schema import (
    BackgroundConfig,
    BackgroundMovement,
    BlendMode,
    ColorStop,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
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
        assert bg.movement.type == "none"

    def test_video_overlay_defaults(self):
        ov = VideoOverlayConfig()
        assert ov.enabled is False
        assert ov.video_path is None
        assert ov.blend_mode == OverlayBlendMode.ADDITIVE
        assert ov.opacity == 1.0
        assert ov.rotation == 0.0
        assert ov.mirror_x is False
        assert ov.mirror_y is False

    def test_preset_has_video_overlay(self):
        preset = Preset(
            name="Overlay Test",
            visualization=VisualizationParams(visualization_type="waveform"),
            video_overlay=VideoOverlayConfig(
                enabled=True,
                video_path="/tmp/particles.webm",
                blend_mode=OverlayBlendMode.SCREEN,
                opacity=0.8,
            ),
        )
        assert preset.video_overlay.enabled is True
        assert preset.video_overlay.blend_mode == OverlayBlendMode.SCREEN

    def test_preset_roundtrip_with_new_fields(self):
        preset = Preset(
            name="Full",
            visualization=VisualizationParams(visualization_type="spectrum_bars"),
            background=BackgroundConfig(
                type="video",
                video_path="/tmp/bg.mp4",
                rotation=180.0,
                mirror_x=True,
                movement=BackgroundMovement(
                    type="drift", speed=2.0, angle=90.0, clamp_to_frame=True,
                ),
            ),
            video_overlay=VideoOverlayConfig(
                enabled=True, opacity=0.5,
                rotation=90.0, mirror_x=True, mirror_y=True,
            ),
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.background.type == "video"
        assert restored.background.rotation == 180.0
        assert restored.background.mirror_x is True
        assert restored.background.movement.type == "drift"
        assert restored.background.movement.angle == 90.0
        assert restored.background.movement.clamp_to_frame is True
        assert restored.video_overlay.enabled is True
        assert restored.video_overlay.opacity == 0.5
        assert restored.video_overlay.rotation == 90.0
        assert restored.video_overlay.mirror_x is True
        assert restored.video_overlay.mirror_y is True

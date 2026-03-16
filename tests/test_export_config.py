"""Tests for ExportConfig backward compatibility and ProjectSettings new fields."""

from pathlib import Path

from wavern.core.export import ExportConfig
from wavern.presets.schema import ProjectSettings


class TestExportConfigBackwardCompat:
    def test_construct_with_original_fields_only(self):
        """ExportConfig should work with just the original fields."""
        config = ExportConfig(
            output_path=Path("/tmp/out.mp4"),
            resolution=(1920, 1080),
            fps=60,
            video_codec="libx264",
            container="mp4",
            crf=18,
        )
        assert config.output_path == Path("/tmp/out.mp4")
        assert config.video_codec == "libx264"
        assert config.crf == 18

    def test_new_fields_have_defaults(self):
        config = ExportConfig(output_path=Path("/tmp/out.mp4"))
        assert config.encoder_speed == "medium"
        assert config.audio_bitrate == "192k"
        assert config.quality_preset == "high"
        assert config.prores_profile == 3
        assert config.gif_max_colors == 256
        assert config.gif_dither is True
        assert config.gif_loop == 0
        assert config.gif_scale == 1.0
        assert config.hw_accel == "auto"

    def test_all_fields_settable(self):
        config = ExportConfig(
            output_path=Path("/tmp/out.webm"),
            container="webm",
            video_codec="libvpx-vp9",
            crf=14,
            encoder_speed="2",
            audio_bitrate="320k",
            quality_preset="very_high",
            prores_profile=5,
            gif_max_colors=128,
            gif_dither=False,
            gif_loop=3,
            gif_scale=0.5,
        )
        assert config.encoder_speed == "2"
        assert config.audio_bitrate == "320k"
        assert config.gif_max_colors == 128
        assert config.gif_dither is False
        assert config.gif_loop == 3
        assert config.gif_scale == 0.5


class TestProjectSettingsNewFields:
    def test_defaults(self):
        ps = ProjectSettings()
        assert ps.video_codec == ""
        assert ps.quality_preset == "high"
        assert ps.encoder_speed == "medium"
        assert ps.audio_bitrate == "192k"
        assert ps.prores_profile == 3
        assert ps.gif_max_colors == 256
        assert ps.gif_dither is True
        assert ps.gif_loop == 0
        assert ps.gif_scale == 1.0
        assert ps.hw_accel == "auto"

    def test_backward_compat_original_fields(self):
        """Constructing with just original fields should still work."""
        ps = ProjectSettings(
            resolution=(1280, 720),
            fps=30,
            container="webm",
            crf=23,
        )
        assert ps.resolution == (1280, 720)
        assert ps.fps == 30
        assert ps.container == "webm"
        assert ps.crf == 23
        # New fields should have defaults
        assert ps.quality_preset == "high"

    def test_json_roundtrip(self):
        ps = ProjectSettings(
            resolution=(2560, 1440),
            fps=120,
            container="mov",
            crf=14,
            video_codec="prores_ks",
            quality_preset="very_high",
            encoder_speed="slow",
            audio_bitrate="320k",
            prores_profile=4,
            gif_max_colors=128,
            gif_dither=False,
            gif_loop=5,
            gif_scale=0.5,
        )
        json_str = ps.model_dump_json()
        restored = ProjectSettings.model_validate_json(json_str)
        assert restored.resolution == (2560, 1440)
        assert restored.container == "mov"
        assert restored.video_codec == "prores_ks"
        assert restored.quality_preset == "very_high"
        assert restored.encoder_speed == "slow"
        assert restored.audio_bitrate == "320k"
        assert restored.prores_profile == 4
        assert restored.gif_max_colors == 128
        assert restored.gif_dither is False
        assert restored.gif_loop == 5
        assert restored.gif_scale == 0.5

    def test_all_new_fields_settable(self):
        ps = ProjectSettings(
            video_codec="libaom-av1",
            quality_preset="lowest",
            encoder_speed="8",
            audio_bitrate="128k",
            prores_profile=0,
            gif_max_colors=64,
            gif_dither=False,
            gif_loop=10,
            gif_scale=0.25,
        )
        assert ps.video_codec == "libaom-av1"
        assert ps.quality_preset == "lowest"
        assert ps.encoder_speed == "8"
        assert ps.audio_bitrate == "128k"
        assert ps.prores_profile == 0
        assert ps.gif_max_colors == 64
        assert ps.gif_scale == 0.25

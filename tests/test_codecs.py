"""Tests for the codec/container registry."""

import pytest

from wavern.core.codecs import (
    AUDIO_BITRATE_OPTIONS,
    CONTAINER_CODECS,
    ENCODER_SPEEDS,
    QUALITY_PRESETS,
    get_codec_family,
    get_codecs_for_container,
    get_default_codec,
    get_quality_settings,
    supports_alpha,
    supports_audio,
)


class TestContainerCodecs:
    def test_all_containers_have_codecs(self):
        for container, codecs in CONTAINER_CODECS.items():
            assert len(codecs) > 0, f"{container} has no codecs"

    def test_known_containers(self):
        assert set(CONTAINER_CODECS.keys()) == {"mp4", "webm", "mov", "gif"}

    def test_get_codecs_for_container(self):
        mp4_codecs = get_codecs_for_container("mp4")
        assert len(mp4_codecs) == 2
        codec_ids = [c.codec_id for c in mp4_codecs]
        assert "libx264" in codec_ids
        assert "libx265" in codec_ids

    def test_get_codecs_for_unknown_container(self):
        assert get_codecs_for_container("avi") == []


class TestDefaultCodec:
    @pytest.mark.parametrize("container,expected", [
        ("mp4", "libx264"),
        ("webm", "libvpx-vp9"),
        ("mov", "prores_ks"),
        ("gif", "gif"),
    ])
    def test_default_codec(self, container: str, expected: str):
        assert get_default_codec(container) == expected

    def test_unknown_container_raises(self):
        with pytest.raises(ValueError, match="Unknown container"):
            get_default_codec("avi")


class TestAlphaSupport:
    @pytest.mark.parametrize("container,codec,expected", [
        ("mp4", "libx264", False),
        ("mp4", "libx265", False),
        ("webm", "libvpx-vp9", True),
        ("webm", "libaom-av1", True),
        ("mov", "prores_ks", True),
        ("gif", "gif", False),
    ])
    def test_supports_alpha(self, container: str, codec: str, expected: bool):
        assert supports_alpha(container, codec) == expected

    def test_unknown_codec_returns_false(self):
        assert supports_alpha("mp4", "unknown_codec") is False


class TestAudioSupport:
    @pytest.mark.parametrize("container,expected", [
        ("mp4", True),
        ("webm", True),
        ("mov", True),
        ("gif", False),
    ])
    def test_supports_audio(self, container: str, expected: bool):
        assert supports_audio(container) == expected


class TestQualityPresets:
    def test_all_presets_exist(self):
        expected = {"highest", "very_high", "high", "medium", "low", "lowest"}
        assert set(QUALITY_PRESETS.keys()) == expected

    def test_presets_have_required_keys(self):
        required = {"crf", "x264_preset", "x265_preset", "vp9_speed",
                     "av1_cpu_used", "prores_profile"}
        for name, preset in QUALITY_PRESETS.items():
            assert required.issubset(set(preset.keys())), (
                f"Preset '{name}' missing keys: {required - set(preset.keys())}"
            )

    def test_crf_ordering(self):
        """Higher quality presets should have lower CRF values."""
        ordered = ["highest", "very_high", "high", "medium", "low", "lowest"]
        crfs = [QUALITY_PRESETS[name]["crf"] for name in ordered]
        assert crfs == sorted(crfs), "CRF values should increase from highest to lowest"

    def test_get_quality_settings_x264(self):
        result = get_quality_settings("high", "libx264")
        assert result["crf"] == 18
        assert result["encoder_speed"] == "medium"
        assert "prores_profile" not in result

    def test_get_quality_settings_vp9(self):
        result = get_quality_settings("medium", "libvpx-vp9")
        assert result["crf"] == 23
        assert result["encoder_speed"] == "4"

    def test_get_quality_settings_av1(self):
        result = get_quality_settings("low", "libaom-av1")
        assert result["crf"] == 28
        assert result["encoder_speed"] == "6"

    def test_get_quality_settings_prores(self):
        result = get_quality_settings("very_high", "prores_ks")
        assert result["prores_profile"] == 4
        assert "crf" not in result

    def test_get_quality_settings_unknown_preset(self):
        with pytest.raises(ValueError, match="Unknown quality preset"):
            get_quality_settings("ultra_mega", "libx264")


class TestCodecFamily:
    @pytest.mark.parametrize("codec_id,family", [
        ("libx264", "x264"),
        ("libx265", "x265"),
        ("libvpx-vp9", "vp9"),
        ("libaom-av1", "av1"),
        ("prores_ks", "prores"),
        ("gif", "gif"),
    ])
    def test_codec_family(self, codec_id: str, family: str):
        assert get_codec_family(codec_id) == family

    def test_unknown_codec_family(self):
        assert get_codec_family("unknown") == ""


class TestEncoderSpeeds:
    def test_x264_speeds(self):
        speeds = ENCODER_SPEEDS["x264"]
        assert "ultrafast" in speeds
        assert "medium" in speeds
        assert "veryslow" in speeds

    def test_prores_no_speeds(self):
        assert ENCODER_SPEEDS["prores"] == []

    def test_gif_no_speeds(self):
        assert ENCODER_SPEEDS["gif"] == []


class TestAudioBitrates:
    def test_options(self):
        assert AUDIO_BITRATE_OPTIONS == ["128k", "192k", "256k", "320k"]

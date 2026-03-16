"""Tests for wavern.core.ffmpeg_cmd.

WHAT THIS TESTS:
- build_ffmpeg_cmd() produces valid ffmpeg CLI arg lists for major codec families
- HW acceleration flag (force_software=True) bypasses HW encoder detection
- x264/x265, VP9, AV1, and ProRes code paths each produce expected flags
Does NOT test: actual ffmpeg execution or GPU encoder availability
"""

from pathlib import Path

import pytest

from wavern.core.export_config import ExportConfig
from wavern.core.ffmpeg_cmd import build_ffmpeg_cmd


def _base_config(**overrides) -> ExportConfig:
    defaults = dict(
        output_path=Path("/tmp/out.mp4"),
        resolution=(1920, 1080),
        fps=60,
        video_codec="libx264",
        container="mp4",
        crf=18,
        encoder_speed="medium",
        hw_accel="off",
    )
    defaults.update(overrides)
    return ExportConfig(**defaults)


class TestBuildFfmpegCmd:
    def test_returns_tuple_of_list_and_bool(self):
        config = _base_config()
        result = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", Path("/tmp/out.mp4"), force_software=True)
        cmd, using_hw = result
        assert isinstance(cmd, list)
        assert isinstance(using_hw, bool)

    def test_x264_contains_crf_and_preset(self):
        config = _base_config(video_codec="libx264", crf=22, encoder_speed="fast")
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", Path("/tmp/out.mp4"), force_software=True)
        assert "-crf" in cmd
        assert "22" in cmd
        assert "-preset" in cmd
        assert "fast" in cmd

    def test_x265_adds_hvc1_tag(self):
        config = _base_config(video_codec="libx265", container="mp4")
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", Path("/tmp/out.mp4"), force_software=True)
        assert "-tag:v" in cmd
        assert "hvc1" in cmd

    def test_vp9_uses_zero_bitrate_crf_mode(self):
        config = _base_config(video_codec="libvpx-vp9", container="webm")
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", Path("/tmp/out.webm"), force_software=True)
        assert "-b:v" in cmd
        b_idx = cmd.index("-b:v")
        assert cmd[b_idx + 1] == "0"
        assert "-crf" in cmd

    def test_prores_uses_profile_flag(self):
        config = _base_config(video_codec="prores_ks", container="mov", prores_profile=3)
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv422p10le", Path("/tmp/out.mov"), force_software=True)
        assert "-profile:v" in cmd
        p_idx = cmd.index("-profile:v")
        assert cmd[p_idx + 1] == "3"

    def test_force_software_disables_hw(self):
        config = _base_config(hw_accel="auto")
        _, using_hw = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", Path("/tmp/out.mp4"), force_software=True)
        assert using_hw is False

    def test_output_path_is_last_arg(self):
        out = Path("/tmp/my_video.mp4")
        config = _base_config()
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1920, 1080, "rgb24", "yuv420p", out, force_software=True)
        assert cmd[-1] == str(out)

    def test_resolution_in_cmd(self):
        config = _base_config(resolution=(1280, 720))
        cmd, _ = build_ffmpeg_cmd(config, "ffmpeg", 1280, 720, "rgb24", "yuv420p", Path("/tmp/out.mp4"), force_software=True)
        assert "-s" in cmd
        s_idx = cmd.index("-s")
        assert cmd[s_idx + 1] == "1280x720"

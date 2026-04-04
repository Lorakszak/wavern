"""Tests for wavern.core.video_concat.

WHAT THIS TESTS:
- probe_video_clip() extracts correct metadata from a PyAV-created video
- probe_video_clip() raises ValueError for non-existent files
- detect_mismatches() correctly identifies resolution and fps mismatches
- detect_mismatches() returns empty list when clips match target
- detect_mismatches() respects 1% fps tolerance (29.97 vs 30)
- resolve_audio_codec() returns correct codec per container
- build_concat_cmd() produces valid ffmpeg command structure
- build_concat_cmd() injects fade/afade filters when fade durations > 0
- ExportConfig intro/outro fields default to None/True
- ExportConfig fade fields default to 0.0

Does NOT test: actual ffmpeg execution (see test_concat_integration)
"""

from pathlib import Path

import av
import numpy as np

from wavern.core.export_config import ExportConfig
from wavern.core.video_concat import (
    ConcatTarget,
    VideoClipInfo,
    build_concat_cmd,
    detect_mismatches,
    probe_video_clip,
    resolve_audio_codec,
)


def _create_test_video(
    path: Path,
    width: int = 320,
    height: int = 240,
    fps: int = 30,
    duration_frames: int = 30,
    with_audio: bool = False,
) -> None:
    """Create a minimal test video file using PyAV."""
    container = av.open(str(path), mode="w")
    vstream = container.add_stream("libx264", rate=fps)
    vstream.width = width
    vstream.height = height
    vstream.pix_fmt = "yuv420p"

    astream = None
    if with_audio:
        astream = container.add_stream("aac", rate=44100)
        astream.layout = "stereo"

    for i in range(duration_frames):
        frame = av.VideoFrame.from_ndarray(
            np.zeros((height, width, 3), dtype=np.uint8), format="rgb24"
        )
        frame.pts = i
        for packet in vstream.encode(frame):
            container.mux(packet)

        if astream is not None:
            aframe = av.AudioFrame.from_ndarray(
                np.zeros((2, 1024), dtype=np.float32), format="fltp", layout="stereo"
            )
            aframe.sample_rate = 44100
            aframe.pts = i * 1024
            for packet in astream.encode(aframe):
                container.mux(packet)

    for packet in vstream.encode():
        container.mux(packet)
    if astream is not None:
        for packet in astream.encode():
            container.mux(packet)

    container.close()


class TestProbeVideoClip:
    def test_probe_video_clip_metadata(self, tmp_path: Path) -> None:
        """probe_video_clip extracts correct width/height/fps/has_audio."""
        video_path = tmp_path / "test.mp4"
        _create_test_video(video_path, width=640, height=480, fps=24, with_audio=True)

        info = probe_video_clip(video_path)
        assert info.path == video_path
        assert info.width == 640
        assert info.height == 480
        assert abs(info.fps - 24.0) < 1.0
        assert info.has_audio is True
        assert info.audio_codec is not None
        assert info.audio_sample_rate > 0
        assert info.duration > 0

    def test_probe_video_clip_no_audio(self, tmp_path: Path) -> None:
        """probe_video_clip correctly identifies video without audio."""
        video_path = tmp_path / "silent.mp4"
        _create_test_video(video_path, with_audio=False)

        info = probe_video_clip(video_path)
        assert info.has_audio is False
        assert info.audio_codec is None
        assert info.audio_sample_rate == 0

    def test_probe_video_clip_nonexistent_raises(self) -> None:
        """probe_video_clip raises ValueError for non-existent file."""
        import pytest

        with pytest.raises(ValueError, match="Cannot open video"):
            probe_video_clip(Path("/nonexistent/video.mp4"))


class TestDetectMismatches:
    def _make_clip(
        self, width: int = 1920, height: int = 1080, fps: float = 60.0,
    ) -> VideoClipInfo:
        return VideoClipInfo(
            path=Path("/fake.mp4"), width=width, height=height, fps=fps,
            duration=10.0, has_audio=True, video_codec="h264",
            audio_codec="aac", audio_sample_rate=44100,
        )

    def test_detect_mismatches_resolution(self) -> None:
        clip = self._make_clip(width=640, height=480)
        mismatches = detect_mismatches(
            [("intro", clip)], (1920, 1080), 60,
        )
        assert len(mismatches) == 1
        assert mismatches[0].clip_label == "intro"
        assert mismatches[0].resolution_match is False
        assert mismatches[0].fps_match is True

    def test_detect_mismatches_fps(self) -> None:
        clip = self._make_clip(fps=30.0)
        mismatches = detect_mismatches(
            [("outro", clip)], (1920, 1080), 60,
        )
        assert len(mismatches) == 1
        assert mismatches[0].fps_match is False
        assert mismatches[0].resolution_match is True

    def test_detect_mismatches_matching(self) -> None:
        clip = self._make_clip()
        mismatches = detect_mismatches(
            [("intro", clip)], (1920, 1080), 60,
        )
        assert mismatches == []

    def test_detect_mismatches_fps_tolerance(self) -> None:
        """29.97 vs 30 should not be a mismatch (within 1% tolerance)."""
        clip = self._make_clip(fps=29.97)
        mismatches = detect_mismatches(
            [("intro", clip)], (1920, 1080), 30,
        )
        assert mismatches == []

    def test_detect_mismatches_fps_tolerance_high_fps(self) -> None:
        """59.94 vs 60 should not be a mismatch."""
        clip = self._make_clip(fps=59.94)
        mismatches = detect_mismatches(
            [("intro", clip)], (1920, 1080), 60,
        )
        assert mismatches == []

    def test_detect_mismatches_both(self) -> None:
        clip = self._make_clip(width=1280, height=720, fps=30.0)
        mismatches = detect_mismatches(
            [("intro", clip)], (1920, 1080), 60,
        )
        assert len(mismatches) == 1
        assert mismatches[0].resolution_match is False
        assert mismatches[0].fps_match is False


class TestResolveAudioCodec:
    def test_webm_returns_libopus(self) -> None:
        assert resolve_audio_codec("webm", "aac") == "libopus"

    def test_mov_returns_pcm(self) -> None:
        assert resolve_audio_codec("mov", "libopus") == "pcm_s16le"

    def test_mp4_passthrough(self) -> None:
        assert resolve_audio_codec("mp4", "aac") == "aac"

    def test_other_passthrough(self) -> None:
        assert resolve_audio_codec("mkv", "libopus") == "libopus"


class TestBuildConcatCmd:
    def _target(self) -> ConcatTarget:
        return ConcatTarget(
            resolution=(1920, 1080), fps=60, video_codec="libx264",
            audio_codec="aac", audio_bitrate="192k", pixel_format="yuv420p",
            container="mp4", crf=18,
        )

    def test_basic_structure(self, tmp_path: Path) -> None:
        seg1 = tmp_path / "intro.mp4"
        seg2 = tmp_path / "main.mp4"
        output = tmp_path / "out.mp4"

        cmd = build_concat_cmd(
            "ffmpeg", [seg1, seg2], [True, True], [True, True],
            self._target(), output,
        )
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-filter_complex" in cmd
        assert "-map" in cmd
        assert str(output) in cmd
        # Should have 2 -i inputs
        i_count = sum(1 for x in cmd if x == "-i")
        assert i_count == 2

    def test_vp9_has_bv_zero(self, tmp_path: Path) -> None:
        target = ConcatTarget(
            resolution=(1920, 1080), fps=60, video_codec="libvpx-vp9",
            audio_codec="libopus", audio_bitrate="192k", pixel_format="yuv420p",
            container="webm", crf=18,
        )
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "a.webm"], [True], [True],
            target, tmp_path / "out.webm",
        )
        assert "-b:v" in cmd
        bv_idx = cmd.index("-b:v")
        assert cmd[bv_idx + 1] == "0"


class TestBuildConcatCmdFades:
    """Tests for fade-in/fade-out filter injection in build_concat_cmd."""

    def _target(self) -> ConcatTarget:
        return ConcatTarget(
            resolution=(1920, 1080), fps=60, video_codec="libx264",
            audio_codec="aac", audio_bitrate="192k", pixel_format="yuv420p",
            container="mp4", crf=18,
        )

    def test_no_fades_no_fade_filter(self, tmp_path: Path) -> None:
        """When all fades are 0, no fade/afade filters appear."""
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "a.mp4", tmp_path / "b.mp4"],
            [True, True], [True, True], self._target(), tmp_path / "out.mp4",
            fade_in_durations=[0.0, 0.0], fade_out_durations=[0.0, 0.0],
            segment_durations=[5.0, 5.0],
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "fade=" not in fc
        assert "afade=" not in fc

    def test_intro_fade_in(self, tmp_path: Path) -> None:
        """Fade-in on first segment produces fade=t=in filter."""
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "intro.mp4", tmp_path / "main.mp4"],
            [True, True], [True, True], self._target(), tmp_path / "out.mp4",
            fade_in_durations=[1.5, 0.0], fade_out_durations=[0.0, 0.0],
            segment_durations=[5.0, 10.0],
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "fade=t=in:st=0:d=1.5" in fc
        assert "afade=t=in:st=0:d=1.5" in fc

    def test_outro_fade_out(self, tmp_path: Path) -> None:
        """Fade-out on second segment produces fade=t=out filter with correct start."""
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "main.mp4", tmp_path / "outro.mp4"],
            [True, True], [True, True], self._target(), tmp_path / "out.mp4",
            fade_in_durations=[0.0, 0.0], fade_out_durations=[0.0, 2.0],
            segment_durations=[10.0, 5.0],
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        # fade-out start = duration - fade_out = 5.0 - 2.0 = 3.0
        assert "fade=t=out:st=3.0:d=2.0" in fc
        assert "afade=t=out:st=3.0:d=2.0" in fc

    def test_both_fades_on_segment(self, tmp_path: Path) -> None:
        """A segment can have both fade-in and fade-out."""
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "intro.mp4"],
            [True], [True], self._target(), tmp_path / "out.mp4",
            fade_in_durations=[1.0], fade_out_durations=[1.0],
            segment_durations=[5.0],
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "fade=t=in:st=0:d=1.0" in fc
        assert "fade=t=out:st=4.0:d=1.0" in fc

    def test_no_afade_on_silent_segment(self, tmp_path: Path) -> None:
        """Segments without audio use anullsrc; afade is not applied."""
        cmd = build_concat_cmd(
            "ffmpeg", [tmp_path / "silent.mp4"],
            [True], [False], self._target(), tmp_path / "out.mp4",
            fade_in_durations=[1.0], fade_out_durations=[0.0],
            segment_durations=[5.0],
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "fade=t=in:st=0:d=1.0" in fc
        assert "afade=" not in fc


class TestExportConfigConcatFields:
    def test_defaults_none(self) -> None:
        config = ExportConfig(output_path=Path("/tmp/out.mp4"))
        assert config.intro_path is None
        assert config.outro_path is None
        assert config.intro_keep_audio is True
        assert config.outro_keep_audio is True

    def test_fields_settable(self) -> None:
        config = ExportConfig(
            output_path=Path("/tmp/out.mp4"),
            intro_path=Path("/tmp/intro.mp4"),
            outro_path=Path("/tmp/outro.mp4"),
            intro_keep_audio=False,
            outro_keep_audio=True,
        )
        assert config.intro_path == Path("/tmp/intro.mp4")
        assert config.outro_path == Path("/tmp/outro.mp4")
        assert config.intro_keep_audio is False
        assert config.outro_keep_audio is True

    def test_fade_defaults_zero(self) -> None:
        config = ExportConfig(output_path=Path("/tmp/out.mp4"))
        assert config.intro_fade_in == 0.0
        assert config.intro_fade_out == 0.0
        assert config.outro_fade_in == 0.0
        assert config.outro_fade_out == 0.0

    def test_fade_fields_settable(self) -> None:
        config = ExportConfig(
            output_path=Path("/tmp/out.mp4"),
            intro_fade_in=1.5,
            intro_fade_out=2.0,
            outro_fade_in=0.5,
            outro_fade_out=3.0,
        )
        assert config.intro_fade_in == 1.5
        assert config.intro_fade_out == 2.0
        assert config.outro_fade_in == 0.5
        assert config.outro_fade_out == 3.0

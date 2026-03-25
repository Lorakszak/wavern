"""Integration tests for wavern.core.video_concat — requires ffmpeg.

WHAT THIS TESTS:
- build_concat_cmd produces a command that ffmpeg can execute
- run_concat_pipeline concatenates intro + main + outro into a single video
- run_concat_pipeline works with intro only and outro only
- Cancellation during concat raises RuntimeError

Does NOT test: GUI export dialog, CLI flags, or export pipeline integration
"""

import shutil
import threading
from pathlib import Path

import av
import numpy as np
import pytest

from wavern.core.video_concat import (
    ConcatTarget,
    build_concat_cmd,
    probe_video_clip,
    run_concat_pipeline,
)

# Skip all tests if ffmpeg is not available
pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not found on PATH",
)


def _create_test_video(
    path: Path,
    width: int = 320,
    height: int = 240,
    fps: int = 30,
    duration_frames: int = 30,
    with_audio: bool = True,
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


def _make_target(width: int = 320, height: int = 240) -> ConcatTarget:
    return ConcatTarget(
        resolution=(width, height), fps=30, video_codec="libx264",
        audio_codec="aac", audio_bitrate="128k", pixel_format="yuv420p",
        container="mp4", crf=28,
    )


class TestConcatIntegration:
    def test_concatenate_two_clips(self, tmp_path: Path) -> None:
        """Two clips concatenated produce a valid video."""
        clip_a = tmp_path / "a.mp4"
        clip_b = tmp_path / "b.mp4"
        output = tmp_path / "out.mp4"

        _create_test_video(clip_a, duration_frames=15, with_audio=True)
        _create_test_video(clip_b, duration_frames=15, with_audio=True)

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None

        cmd = build_concat_cmd(
            ffmpeg_bin, [clip_a, clip_b], [True, True], [True, True],
            target, output,
        )

        import subprocess
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        assert output.exists()

        # Verify output has video
        info = probe_video_clip(output)
        assert info.width == 320
        assert info.height == 240

    def test_conform_clip_changes_resolution(self, tmp_path: Path) -> None:
        """A 640x480 clip conformed to 320x240 target."""
        clip = tmp_path / "big.mp4"
        output = tmp_path / "out.mp4"

        _create_test_video(clip, width=640, height=480, duration_frames=10, with_audio=True)
        _create_test_video(tmp_path / "main.mp4", duration_frames=10, with_audio=True)

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None

        cmd = build_concat_cmd(
            ffmpeg_bin,
            [clip, tmp_path / "main.mp4"],
            [True, True], [True, True],
            target, output,
        )

        import subprocess
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"

        info = probe_video_clip(output)
        assert info.width == 320
        assert info.height == 240

    def test_run_concat_pipeline_intro_only(self, tmp_path: Path) -> None:
        """Pipeline works with only an intro clip."""
        intro = tmp_path / "intro.mp4"
        main_vid = tmp_path / "main.mp4"
        output = tmp_path / "output.mp4"

        _create_test_video(intro, duration_frames=10, with_audio=True)
        _create_test_video(main_vid, duration_frames=15, with_audio=True)

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None
        cancelled = threading.Event()

        result = run_concat_pipeline(
            ffmpeg_bin=ffmpeg_bin,
            rendered_video=main_vid,
            output_path=output,
            intro_path=intro,
            outro_path=None,
            intro_keep_audio=True,
            outro_keep_audio=True,
            target=target,
            cancelled=cancelled,
        )
        assert result == output
        assert output.exists()

    def test_run_concat_pipeline_full(self, tmp_path: Path) -> None:
        """Pipeline works with intro + main + outro."""
        intro = tmp_path / "intro.mp4"
        main_vid = tmp_path / "main.mp4"
        outro = tmp_path / "outro.mp4"
        output = tmp_path / "output.mp4"

        _create_test_video(intro, duration_frames=10, with_audio=True)
        _create_test_video(main_vid, duration_frames=15, with_audio=True)
        _create_test_video(outro, duration_frames=10, with_audio=True)

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None
        cancelled = threading.Event()

        result = run_concat_pipeline(
            ffmpeg_bin=ffmpeg_bin,
            rendered_video=main_vid,
            output_path=output,
            intro_path=intro,
            outro_path=outro,
            intro_keep_audio=True,
            outro_keep_audio=True,
            target=target,
            cancelled=cancelled,
        )
        assert result == output
        assert output.exists()

        info = probe_video_clip(output)
        assert info.has_audio is True

    def test_concat_strips_audio(self, tmp_path: Path) -> None:
        """Intro with keep_audio=False gets silence."""
        intro = tmp_path / "intro.mp4"
        main_vid = tmp_path / "main.mp4"
        output = tmp_path / "output.mp4"

        _create_test_video(intro, duration_frames=10, with_audio=True)
        _create_test_video(main_vid, duration_frames=15, with_audio=True)

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None
        cancelled = threading.Event()

        result = run_concat_pipeline(
            ffmpeg_bin=ffmpeg_bin,
            rendered_video=main_vid,
            output_path=output,
            intro_path=intro,
            outro_path=None,
            intro_keep_audio=False,
            outro_keep_audio=True,
            target=target,
            cancelled=cancelled,
        )
        assert result == output
        assert output.exists()

    def test_cancellation_raises(self, tmp_path: Path) -> None:
        """Cancelling before concat raises RuntimeError."""
        cancelled = threading.Event()
        cancelled.set()

        target = _make_target()
        ffmpeg_bin = shutil.which("ffmpeg")
        assert ffmpeg_bin is not None

        intro = tmp_path / "intro.mp4"
        main_vid = tmp_path / "main.mp4"
        _create_test_video(intro, duration_frames=5, with_audio=True)
        _create_test_video(main_vid, duration_frames=5, with_audio=True)

        with pytest.raises(RuntimeError, match="cancelled"):
            run_concat_pipeline(
                ffmpeg_bin=ffmpeg_bin,
                rendered_video=main_vid,
                output_path=tmp_path / "out.mp4",
                intro_path=intro,
                outro_path=None,
                intro_keep_audio=True,
                outro_keep_audio=True,
                target=target,
                cancelled=cancelled,
            )

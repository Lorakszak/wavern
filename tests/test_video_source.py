"""Tests for VideoSource decoder."""

import tempfile
from pathlib import Path

import av
import numpy as np
import pytest

from wavern.core.video_source import VideoSource


@pytest.fixture
def tiny_video(tmp_path: Path) -> Path:
    """Create a 10-frame test video (320x240, 10fps, 1 second)."""
    video_path = tmp_path / "test.mp4"
    container = av.open(str(video_path), mode="w")
    stream = container.add_stream("libx264", rate=10)
    stream.width = 320
    stream.height = 240
    stream.pix_fmt = "yuv420p"

    for i in range(10):
        # Each frame gets a unique brightness so we can verify seeking
        brightness = int(25 * i)
        img = np.full((240, 320, 3), brightness, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = i
        for packet in stream.encode(frame):
            container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return video_path


class TestVideoSource:
    def test_open_and_metadata(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        assert vs.size == (320, 240)
        assert vs.duration > 0
        vs.close()

    def test_get_frame_returns_rgba(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        frame = vs.get_frame(0.0)
        assert frame.dtype == np.uint8
        assert frame.shape == (240, 320, 4)
        vs.close()

    def test_sequential_access(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        # Get first and last frame — these should differ (brightness 0 vs 225)
        first = vs.get_frame(0.0).copy()
        vs.reset()
        # Seek far enough that we get a different frame
        last = vs.get_frame(0.8).copy()
        assert not np.array_equal(first, last)
        vs.close()

    def test_looping(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        dur = vs.duration
        # Request timestamp beyond duration — should loop
        frame = vs.get_frame(dur + 0.05, loop=True)
        assert frame.shape == (240, 320, 4)
        vs.close()

    def test_reset(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        vs.get_frame(0.5)
        vs.reset()
        frame = vs.get_frame(0.0)
        assert frame.shape == (240, 320, 4)
        vs.close()

    def test_close_and_reopen(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        vs.get_frame(0.0)
        vs.close()
        # Should be able to reopen
        vs.open()
        frame = vs.get_frame(0.0)
        assert frame.shape == (240, 320, 4)
        vs.close()

    def test_not_open_raises(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        with pytest.raises(RuntimeError, match="not open"):
            vs.get_frame(0.0)

    def test_cached_frame_reuse(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        f1 = vs.get_frame(0.0)
        f2 = vs.get_frame(0.0)
        # Should be the exact same array object (cache hit)
        assert f1 is f2
        vs.close()

    def test_fps_property(self, tiny_video: Path):
        vs = VideoSource(tiny_video)
        vs.open()
        assert vs.fps == pytest.approx(10.0, abs=1.0)
        vs.close()

    def test_probe_fps(self, tiny_video: Path):
        fps = VideoSource.probe_fps(tiny_video)
        assert fps == pytest.approx(10.0, abs=1.0)

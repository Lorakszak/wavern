"""Video frame decoder with seeking, caching, and looping via PyAV."""

import logging
from pathlib import Path

import av
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class VideoSource:
    """Decodes video frames on demand with caching and looping.

    Args:
        video_path: Path to the video file.
    """

    def __init__(self, video_path: str | Path) -> None:
        self._path = Path(video_path)
        self._container: av.container.InputContainer | None = None
        self._stream: av.video.stream.VideoStream | None = None
        self._duration: float = 0.0
        self._size: tuple[int, int] = (0, 0)
        self._fps: float = 30.0
        self._last_frame: NDArray[np.uint8] | None = None
        self._last_pts: int = -1
        self._time_base: float = 1.0

    def open(self) -> None:
        """Open the video file and read stream metadata."""
        if self._container is not None:
            self.close()

        self._container = av.open(str(self._path))
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"

        # Extract metadata
        self._size = (self._stream.codec_context.width, self._stream.codec_context.height)
        self._time_base = float(self._stream.time_base)

        if self._stream.duration is not None:
            self._duration = float(self._stream.duration) * self._time_base
        elif self._container.duration is not None:
            self._duration = float(self._container.duration) / av.time_base
        else:
            self._duration = 0.0

        avg_rate = self._stream.average_rate
        if avg_rate is not None:
            self._fps = float(avg_rate)

        logger.info(
            "Opened video: %s (%dx%d, %.1fs, %.1ffps)",
            self._path.name,
            self._size[0],
            self._size[1],
            self._duration,
            self._fps,
        )

    def close(self) -> None:
        """Release the container and stream resources."""
        if self._container is not None:
            self._container.close()
            self._container = None
        self._stream = None
        self._last_frame = None
        self._last_pts = -1

    @property
    def duration(self) -> float:
        """Video duration in seconds."""
        return self._duration

    @property
    def fps(self) -> float:
        """Video average frame rate."""
        return self._fps

    @property
    def size(self) -> tuple[int, int]:
        """Video dimensions as (width, height)."""
        return self._size

    @staticmethod
    def probe_fps(video_path: str | Path) -> float:
        """Read the video's average frame rate without keeping it open.

        Args:
            video_path: Path to the video file.

        Returns:
            Average FPS as a float, or 0.0 if unreadable.
        """
        try:
            container = av.open(str(video_path))
            try:
                stream = container.streams.video[0]
                rate = stream.average_rate
                return float(rate) if rate is not None else 0.0
            finally:
                container.close()
        except Exception:
            return 0.0

    def get_frame(self, timestamp: float, loop: bool = True) -> NDArray[np.uint8]:
        """Return the RGBA frame at the given timestamp.

        Args:
            timestamp: Time in seconds.
            loop: If True, wraps timestamp via modulo duration.

        Returns:
            RGBA array of shape (H, W, 4) with dtype uint8.

        Raises:
            RuntimeError: If the video is not open.
        """
        if self._container is None or self._stream is None:
            raise RuntimeError("VideoSource is not open — call open() first")

        if loop and self._duration > 0:
            timestamp = timestamp % self._duration

        # Convert timestamp to stream pts
        target_pts = int(timestamp / self._time_base) if self._time_base > 0 else 0

        # Reuse cached frame if same pts
        if self._last_frame is not None and target_pts == self._last_pts:
            return self._last_frame

        # Decide whether to seek or continue sequential decode
        frames_ahead = (target_pts - self._last_pts) / max(
            1, int(1.0 / (self._fps * self._time_base))
        ) if self._last_pts >= 0 else float("inf")

        if frames_ahead < 0 or frames_ahead > 30:
            # Seek to nearest keyframe before target
            self._container.seek(target_pts, stream=self._stream)
            # Flush decoder buffers for clean playback after seek
            # (critical for loop-point seeks to avoid stale frame lag)
            self._stream.codec_context.flush_buffers()

        # Decode forward to the target frame
        best_frame: av.VideoFrame | None = None
        try:
            for frame in self._container.decode(self._stream):
                best_frame = frame
                if frame.pts is not None and frame.pts >= target_pts:
                    break
        except av.error.EOFError:
            pass

        if best_frame is not None:
            arr = best_frame.to_ndarray(format="rgba")
            # Flip vertically: video decoders produce top-down rows but
            # OpenGL textures expect bottom-up (origin at bottom-left).
            arr = np.flipud(arr).copy()
            self._last_frame = arr
            self._last_pts = best_frame.pts if best_frame.pts is not None else target_pts
            return arr

        # Fallback: return cached frame or black
        if self._last_frame is not None:
            return self._last_frame

        return np.zeros((self._size[1], self._size[0], 4), dtype=np.uint8)

    def reset(self) -> None:
        """Reset decoder to the beginning of the video."""
        if self._container is not None and self._stream is not None:
            self._container.seek(0, stream=self._stream)
        self._last_frame = None
        self._last_pts = -1

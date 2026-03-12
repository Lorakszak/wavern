"""Timeline — maps audio time to frame indices and handles sync."""


class Timeline:
    """Maps between audio timestamps and frame indices.

    Used by both the real-time preview and the export pipeline
    to convert between time domains.
    """

    def __init__(self, duration: float, fps: int = 60) -> None:
        self.duration = duration
        self.fps = fps
        self.total_frames = int(duration * fps)

    def frame_to_time(self, frame_index: int) -> float:
        """Convert a frame index to a timestamp in seconds."""
        return frame_index / self.fps

    def time_to_frame(self, timestamp: float) -> int:
        """Convert a timestamp to the nearest frame index."""
        return int(timestamp * self.fps)

    def clamp_time(self, timestamp: float) -> float:
        """Clamp a timestamp to the valid range [0, duration]."""
        return max(0.0, min(timestamp, self.duration))

    def progress(self, timestamp: float) -> float:
        """Get normalized progress [0.0, 1.0] for a timestamp."""
        if self.duration <= 0:
            return 0.0
        return max(0.0, min(timestamp / self.duration, 1.0))

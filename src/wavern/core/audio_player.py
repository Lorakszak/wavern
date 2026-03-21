"""Audio playback via sounddevice with position tracking."""

import logging
import threading

import numpy as np
import sounddevice as sd
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Real-time audio playback with position tracking.

    Uses sounddevice's output stream with a callback to track
    the current playback position accurately.
    """

    def __init__(self) -> None:
        self._audio_data: NDArray[np.float32] | None = None
        self._sample_rate: int = 44100
        self._stream: sd.OutputStream | None = None
        self._position: int = 0  # current sample index
        self._playing: bool = False
        self._volume: float = 1.0
        self._muted: bool = False
        self._lock = threading.Lock()

    @property
    def volume(self) -> float:
        """Playback volume in range [0.0, 1.0]."""
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = value

    def load(self, audio_data: NDArray[np.float32], sample_rate: int) -> None:
        """Load audio data for playback."""
        self.stop()
        self._audio_data = audio_data
        self._sample_rate = sample_rate
        self._position = 0

    def play(self) -> None:
        """Start or resume playback."""
        if self._audio_data is None:
            return

        if self._stream is not None:
            self._stream.close()

        with self._lock:
            self._playing = True
        self._stream = sd.OutputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=1024,
        )
        self._stream.start()

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            self._playing = False
        if self._stream is not None:
            self._stream.stop()

    def stop(self) -> None:
        """Stop playback and reset position."""
        with self._lock:
            self._playing = False
            self._position = 0
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def seek(self, timestamp: float) -> None:
        """Seek to a specific time in seconds."""
        with self._lock:
            self._position = int(timestamp * self._sample_rate)
            if self._audio_data is not None:
                self._position = max(0, min(self._position, len(self._audio_data) - 1))

    def get_position(self) -> float:
        """Get the current playback position in seconds."""
        with self._lock:
            return self._position / self._sample_rate

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def duration(self) -> float:
        if self._audio_data is None:
            return 0.0
        return len(self._audio_data) / self._sample_rate

    def _audio_callback(
        self,
        outdata: NDArray[np.float32],
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Sounddevice callback — fills output buffer and updates position."""
        if status:
            logger.warning("Audio callback status: %s", status)

        if self._audio_data is None or not self._playing:
            outdata.fill(0)
            return

        with self._lock:
            start = self._position
            end = start + frames
            scale = 0.0 if self._muted else self._volume

            if start >= len(self._audio_data):
                outdata.fill(0)
                self._playing = False
                return

            if end > len(self._audio_data):
                valid = len(self._audio_data) - start
                outdata[:valid, 0] = self._audio_data[start : start + valid] * scale
                outdata[valid:, 0] = 0
                self._position = len(self._audio_data)
                self._playing = False
            else:
                outdata[:, 0] = self._audio_data[start:end] * scale
                self._position = end

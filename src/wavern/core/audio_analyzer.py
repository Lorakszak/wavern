"""Audio analysis — FFT, frequency bands, beat detection, spectral features."""

import logging
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


@dataclass
class FrameAnalysis:
    """Analysis results for a single frame of audio.

    Produced by AudioAnalyzer for each render frame. Every visualization
    receives one of these per frame and reads whichever fields it needs.
    """

    timestamp: float
    waveform: NDArray[np.float32]
    fft_magnitudes: NDArray[np.float32]
    fft_frequencies: NDArray[np.float32]
    frequency_bands: dict[str, float]
    amplitude: float
    peak: float
    beat: bool
    beat_intensity: float
    spectral_centroid: float
    spectral_flux: float


FREQUENCY_BANDS: dict[str, tuple[float, float]] = {
    "sub_bass": (20, 60),
    "bass": (60, 250),
    "low_mid": (250, 500),
    "mid": (500, 2000),
    "upper_mid": (2000, 4000),
    "presence": (4000, 6000),
    "brilliance": (6000, 20000),
}


class AudioAnalyzer:
    """Processes loaded audio data and produces per-frame analysis.

    Operates on pre-loaded numpy audio arrays. Call configure() for each
    new audio file before calling analyze_frame().
    """

    def __init__(
        self,
        fft_size: int = 2048,
        hop_size: int = 512,
        smoothing_factor: float = 0.3,
    ) -> None:
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.smoothing_factor = smoothing_factor

        self._audio_data: NDArray[np.float32] | None = None
        self._sample_rate: int = 44100
        self._window: NDArray[np.float64] = np.hanning(fft_size)
        self._prev_magnitudes: NDArray[np.float32] | None = None
        self._beat_timestamps: list[float] = []
        self._beat_threshold_window: list[float] = []

    def configure(self, audio_data: NDArray[np.float32], sample_rate: int) -> None:
        """Prepare analyzer for a specific audio track."""
        self._audio_data = audio_data
        self._sample_rate = sample_rate
        self._prev_magnitudes = None
        self._beat_timestamps = self.precompute_beats()
        logger.info(
            "Analyzer configured: %d samples, %dHz, %d beats detected",
            len(audio_data),
            sample_rate,
            len(self._beat_timestamps),
        )

    def analyze_frame(self, timestamp: float) -> FrameAnalysis:
        """Compute full analysis for the audio window centered at timestamp."""
        if self._audio_data is None:
            raise RuntimeError("AudioAnalyzer not configured — call configure() first")

        center_sample = int(timestamp * self._sample_rate)
        half_window = self.fft_size // 2

        start = max(0, center_sample - half_window)
        end = start + self.fft_size

        if end > len(self._audio_data):
            end = len(self._audio_data)
            start = max(0, end - self.fft_size)

        samples = self._audio_data[start:end]

        # Pad if necessary
        if len(samples) < self.fft_size:
            samples = np.pad(samples, (0, self.fft_size - len(samples)))

        samples = samples.astype(np.float32)

        # Waveform (raw samples for display)
        waveform = samples.copy()

        # FFT
        magnitudes, frequencies = self._compute_fft(samples)

        # Smoothing
        if self._prev_magnitudes is not None and len(self._prev_magnitudes) == len(magnitudes):
            magnitudes = (
                self._prev_magnitudes * self.smoothing_factor
                + magnitudes * (1.0 - self.smoothing_factor)
            ).astype(np.float32)
        self._prev_magnitudes = magnitudes.copy()

        # Frequency bands
        bands = self._compute_frequency_bands(magnitudes, frequencies)

        # Amplitude
        amplitude = float(np.sqrt(np.mean(samples**2)))
        peak = float(np.max(np.abs(samples)))

        # Beat detection
        beat, beat_intensity = self._check_beat(timestamp)

        # Spectral centroid
        mag_sum = np.sum(magnitudes)
        if mag_sum > 1e-10:
            spectral_centroid = float(np.sum(frequencies * magnitudes) / mag_sum)
        else:
            spectral_centroid = 0.0

        # Spectral flux
        if self._prev_magnitudes is not None:
            flux = float(np.sum(np.maximum(magnitudes - self._prev_magnitudes, 0)))
        else:
            flux = 0.0

        return FrameAnalysis(
            timestamp=timestamp,
            waveform=waveform,
            fft_magnitudes=magnitudes,
            fft_frequencies=frequencies,
            frequency_bands=bands,
            amplitude=amplitude,
            peak=peak,
            beat=beat,
            beat_intensity=beat_intensity,
            spectral_centroid=spectral_centroid,
            spectral_flux=flux,
        )

    def precompute_beats(self) -> list[float]:
        """Detect all beat timestamps using onset strength + peak detection."""
        if self._audio_data is None:
            return []

        hop = self.hop_size
        num_frames = (len(self._audio_data) - self.fft_size) // hop + 1

        if num_frames < 2:
            return []

        # Compute onset strength (spectral flux)
        onset_strength = []
        prev_mag = None
        for i in range(num_frames):
            start = i * hop
            frame = self._audio_data[start : start + self.fft_size]
            if len(frame) < self.fft_size:
                frame = np.pad(frame, (0, self.fft_size - len(frame)))

            windowed = frame * self._window
            spectrum = np.abs(np.fft.rfft(windowed))

            if prev_mag is not None:
                flux = np.sum(np.maximum(spectrum - prev_mag, 0))
                onset_strength.append(flux)
            else:
                onset_strength.append(0.0)

            prev_mag = spectrum

        onset_arr = np.array(onset_strength, dtype=np.float32)

        if len(onset_arr) < 3:
            return []

        # Find peaks in onset strength
        mean_strength = np.mean(onset_arr)
        std_strength = np.std(onset_arr)
        threshold = mean_strength + 0.5 * std_strength

        peaks, properties = find_peaks(
            onset_arr,
            height=threshold,
            distance=int(self._sample_rate / hop * 0.15),  # min 150ms between beats
        )

        timestamps = [float(p * hop / self._sample_rate) for p in peaks]
        return timestamps

    def _check_beat(self, timestamp: float) -> tuple[bool, float]:
        """Check if a beat occurs near the given timestamp."""
        if not self._beat_timestamps:
            return False, 0.0

        tolerance = 1.0 / 30.0  # ~1 frame at 30fps

        for bt in self._beat_timestamps:
            if abs(bt - timestamp) < tolerance:
                return True, 1.0

        return False, 0.0

    def _compute_fft(
        self, samples: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """Apply windowed FFT. Returns (magnitudes, frequencies)."""
        windowed = samples * self._window
        spectrum = np.fft.rfft(windowed)
        magnitudes = np.abs(spectrum).astype(np.float32)

        # Normalize
        magnitudes = magnitudes / (self.fft_size / 2)

        frequencies = np.fft.rfftfreq(self.fft_size, 1.0 / self._sample_rate).astype(np.float32)

        return magnitudes, frequencies

    def _compute_frequency_bands(
        self,
        magnitudes: NDArray[np.float32],
        frequencies: NDArray[np.float32],
    ) -> dict[str, float]:
        """Sum magnitudes within each named frequency band."""
        bands: dict[str, float] = {}
        for band_name, (low, high) in FREQUENCY_BANDS.items():
            mask = (frequencies >= low) & (frequencies < high)
            if np.any(mask):
                bands[band_name] = float(np.mean(magnitudes[mask]))
            else:
                bands[band_name] = 0.0
        return bands

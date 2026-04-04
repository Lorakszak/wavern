"""Audio analysis — FFT, frequency bands, beat detection, spectral features."""

import bisect
import logging
import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import uniform_filter1d
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
    fft_magnitudes_db: NDArray[np.float32] = field(default_factory=lambda: np.array([], dtype=np.float32))
    fft_magnitudes_norm: NDArray[np.float32] = field(default_factory=lambda: np.array([], dtype=np.float32))
    frequency_bands_norm: dict[str, float] = field(default_factory=dict)
    amplitude_envelope: float = 0.0
    band_envelopes: dict[str, float] = field(default_factory=dict)


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
        self._prev_raw_magnitudes: NDArray[np.float32] | None = None
        self._beat_timestamps: list[tuple[float, float]] = []
        self._beat_times: list[float] = []

        # Running-peak normalization state
        self._running_peak: float = 1e-10

        # Per-band auto-gain state
        self._band_running_rms: dict[str, float] = {name: 1e-10 for name in FREQUENCY_BANDS}

        # Envelope follower state
        self._amplitude_envelope: float = 0.0
        self._band_envelopes: dict[str, float] = {name: 0.0 for name in FREQUENCY_BANDS}
        self._prev_timestamp: float = 0.0

    def configure(self, audio_data: NDArray[np.float32], sample_rate: int) -> None:
        """Prepare analyzer for a specific audio track."""
        logger.debug(
            "Configuring analyzer: fft_size=%d, hop_size=%d, smoothing=%.2f",
            self.fft_size, self.hop_size, self.smoothing_factor,
        )
        self._audio_data = audio_data
        self._sample_rate = sample_rate
        self._prev_magnitudes = None
        self._prev_raw_magnitudes = None
        self._running_peak = 1e-10
        self._band_running_rms = {name: 1e-10 for name in FREQUENCY_BANDS}
        self._amplitude_envelope = 0.0
        self._band_envelopes = {name: 0.0 for name in FREQUENCY_BANDS}
        self._prev_timestamp = 0.0
        self._beat_timestamps = self.precompute_beats()
        self._beat_times = [bt for bt, _ in self._beat_timestamps]
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

        # Spectral flux (computed from raw magnitudes BEFORE smoothing)
        if self._prev_raw_magnitudes is not None and len(self._prev_raw_magnitudes) == len(magnitudes):
            flux = float(np.sum(np.maximum(magnitudes - self._prev_raw_magnitudes, 0)))
        else:
            flux = 0.0
        self._prev_raw_magnitudes = magnitudes.copy()

        # Smoothing
        if self._prev_magnitudes is not None and len(self._prev_magnitudes) == len(magnitudes):
            magnitudes = (
                self._prev_magnitudes * self.smoothing_factor
                + magnitudes * (1.0 - self.smoothing_factor)
            ).astype(np.float32)
        self._prev_magnitudes = magnitudes.copy()

        # dB-scaled magnitudes (from smoothed)
        magnitudes_db = np.clip(20.0 * np.log10(np.maximum(magnitudes, 1e-10)) + 60.0, 0.0, 60.0) / 60.0
        magnitudes_db = magnitudes_db.astype(np.float32)

        # Running-peak normalization
        dt = timestamp - self._prev_timestamp
        if dt <= 0 or dt > 0.5:
            dt = 1.0 / 60.0
        self._prev_timestamp = timestamp

        current_peak = float(np.max(magnitudes))
        decay = math.exp(-dt / 3.0)
        self._running_peak = max(self._running_peak * decay, current_peak, 1e-10)
        magnitudes_norm = np.clip(magnitudes / self._running_peak, 0.0, 1.0).astype(np.float32)

        # Frequency bands
        bands = self._compute_frequency_bands(magnitudes, frequencies)

        # Per-band auto-gain
        alpha = 0.005
        bands_norm: dict[str, float] = {}
        for name, energy in bands.items():
            self._band_running_rms[name] = (
                self._band_running_rms[name] * (1.0 - alpha) + energy * alpha
            )
            running = max(self._band_running_rms[name], 1e-10)
            bands_norm[name] = min(energy / running, 3.0) / 3.0

        # Amplitude
        amplitude = float(np.sqrt(np.mean(samples**2)))
        peak = float(np.max(np.abs(samples)))

        # Asymmetric envelope followers
        attack_coeff = 1.0 - math.exp(-dt / 0.010)
        release_coeff = 1.0 - math.exp(-dt / 0.200)

        if amplitude > self._amplitude_envelope:
            self._amplitude_envelope += (amplitude - self._amplitude_envelope) * attack_coeff
        else:
            self._amplitude_envelope += (amplitude - self._amplitude_envelope) * release_coeff

        band_envelopes: dict[str, float] = {}
        for name, energy in bands.items():
            prev = self._band_envelopes[name]
            coeff = attack_coeff if energy > prev else release_coeff
            self._band_envelopes[name] += (energy - prev) * coeff
            band_envelopes[name] = self._band_envelopes[name]

        # Beat detection
        beat, beat_intensity = self._check_beat(timestamp)

        # Spectral centroid
        mag_sum = np.sum(magnitudes)
        if mag_sum > 1e-10:
            spectral_centroid = float(np.sum(frequencies * magnitudes) / mag_sum)
        else:
            spectral_centroid = 0.0

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
            fft_magnitudes_db=magnitudes_db,
            fft_magnitudes_norm=magnitudes_norm,
            frequency_bands_norm=bands_norm,
            amplitude_envelope=self._amplitude_envelope,
            band_envelopes=band_envelopes,
        )

    def precompute_beats(self) -> list[tuple[float, float]]:
        """Detect all beat timestamps using bass-weighted onset strength + adaptive threshold."""
        if self._audio_data is None:
            return []

        hop = self.hop_size
        num_frames = (len(self._audio_data) - self.fft_size) // hop + 1

        if num_frames < 2:
            return []

        # Precompute bass mask (<250 Hz) for bass-weighted beat detection
        freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self._sample_rate)
        bass_mask = freqs < 250.0

        # Compute onset strength (bass-weighted spectral flux)
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
                # Bass-weighted flux: only consider sub_bass + bass range
                bass_current = spectrum[bass_mask]
                bass_prev = prev_mag[bass_mask]
                flux = float(np.sum(np.maximum(bass_current - bass_prev, 0)))
                onset_strength.append(flux)
            else:
                onset_strength.append(0.0)

            prev_mag = spectrum

        onset_arr = np.array(onset_strength, dtype=np.float32)

        if len(onset_arr) < 3:
            return []

        # Adaptive windowed threshold (3-second window)
        window_size = max(3, int(3.0 * self._sample_rate / hop))
        # Ensure window_size is odd for uniform_filter1d
        if window_size % 2 == 0:
            window_size += 1

        local_mean = uniform_filter1d(onset_arr.astype(np.float64), size=window_size).astype(
            np.float32
        )
        local_sq_mean = uniform_filter1d(
            (onset_arr.astype(np.float64) ** 2), size=window_size
        ).astype(np.float32)
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean**2, 0.0))
        threshold = local_mean + 0.5 * local_std

        # Mask below threshold
        onset_masked = np.where(onset_arr > threshold, onset_arr, 0.0).astype(np.float32)

        # Find peaks with minimum distance enforcement
        min_distance = max(1, int(self._sample_rate / hop * 0.15))  # min 150ms between beats
        peaks, _ = find_peaks(onset_masked, height=0.0, distance=min_distance)

        if len(peaks) == 0:
            return []

        # Graduated beat intensity: normalize strengths to [0, 1]
        peak_strengths = onset_arr[peaks]
        max_onset = float(np.max(peak_strengths))
        if max_onset < 1e-10:
            return []

        timestamps = [
            (float(p * hop / self._sample_rate), float(onset_arr[p] / max_onset))
            for p in peaks
        ]
        return timestamps

    def _check_beat(self, timestamp: float) -> tuple[bool, float]:
        """Check if a beat occurs near the given timestamp."""
        if not self._beat_timestamps:
            return False, 0.0

        tolerance = 1.0 / 30.0  # ~1 frame at 30fps

        idx = bisect.bisect_left(self._beat_times, timestamp - tolerance)
        while idx < len(self._beat_timestamps):
            bt, strength = self._beat_timestamps[idx]
            if bt > timestamp + tolerance:
                break
            if abs(bt - timestamp) < tolerance:
                return True, strength
            idx += 1

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

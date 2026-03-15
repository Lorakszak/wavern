"""Shared test fixtures."""

import numpy as np
import pytest


@pytest.fixture
def sample_audio() -> tuple[np.ndarray, int]:
    """Generate a simple sine wave for testing."""
    sample_rate = 44100
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    # 440Hz sine + 880Hz harmonic
    audio = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 880 * t)
    return audio.astype(np.float32), sample_rate


@pytest.fixture
def sample_rate() -> int:
    return 44100


@pytest.fixture
def beat_audio() -> tuple[np.ndarray, int]:
    """Generate audio with distinct amplitude bursts at known intervals for beat tests."""
    sample_rate = 44100
    duration = 3.0
    n_samples = int(sample_rate * duration)
    audio = np.zeros(n_samples, dtype=np.float32)

    # Create bursts at 0.5s, 1.0s, 1.5s, 2.0s, 2.5s with varying amplitudes
    burst_times = [0.5, 1.0, 1.5, 2.0, 2.5]
    burst_amplitudes = [0.3, 0.8, 0.5, 1.0, 0.6]
    burst_duration = 0.02  # 20ms bursts

    for t, amp in zip(burst_times, burst_amplitudes):
        start = int(t * sample_rate)
        end = min(start + int(burst_duration * sample_rate), n_samples)
        burst_t = np.linspace(0, burst_duration, end - start, dtype=np.float32)
        # Low-frequency burst (kick-like, 60Hz)
        audio[start:end] += amp * np.sin(2 * np.pi * 60 * burst_t)

    return audio.astype(np.float32), sample_rate


@pytest.fixture
def chirp_audio() -> tuple[np.ndarray, int]:
    """Generate a chirp signal (rising frequency) for spectral flux tests."""
    sample_rate = 44100
    duration = 1.0
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, dtype=np.float32)
    # Chirp from 100Hz to 4000Hz
    freq = 100.0 + (4000.0 - 100.0) * t / duration
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    audio = 0.5 * np.sin(phase)
    return audio.astype(np.float32), sample_rate

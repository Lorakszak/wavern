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

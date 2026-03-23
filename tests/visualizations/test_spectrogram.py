"""Tests for spectrogram-specific logic.

WHAT THIS TESTS:
- _resample_spectrum() produces float32 output of the requested length for linear, log, and mel scales
Does NOT test: registration, PARAM_SCHEMA structure, preset validity (see test_common, test_all_presets),
OpenGL rendering, GPU texture upload, or scrolling animation
"""

import numpy as np

from wavern.visualizations.spectrogram import _resample_spectrum


class TestSpectrogramResample:
    def test_resample_linear_output_length(self) -> None:
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "linear", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_logarithmic_output_length(self) -> None:
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "logarithmic", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_mel_output_length(self) -> None:
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "mel", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_dtype(self) -> None:
        mags = np.ones(512, dtype="f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "linear", 20.0, 16000.0)
        assert out.dtype == np.float32

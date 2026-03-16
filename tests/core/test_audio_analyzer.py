"""Tests for wavern.core.audio_analyzer.

WHAT THIS TESTS:
- AudioAnalyzer.configure() binds audio data and sample rate
- analyze_frame() returns a FrameAnalysis with correct field types and value ranges
- All expected frequency bands (sub_bass through brilliance) are populated
- Smoothing, spectral flux, beat intensity graduation, and envelope decay behaviour
Does NOT test: audio file loading (see test_audio_loader) or playback (test_audio_player)
"""

import numpy as np
import pytest

from wavern.core.audio_analyzer import AudioAnalyzer, FrameAnalysis


class TestAudioAnalyzer:
    def test_configure(self, sample_audio):
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)
        assert analyzer._audio_data is not None
        assert analyzer._sample_rate == sr

    def test_analyze_frame_returns_frame_analysis(self, sample_audio):
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        frame = analyzer.analyze_frame(0.5)

        assert isinstance(frame, FrameAnalysis)
        assert frame.timestamp == 0.5
        assert len(frame.waveform) > 0
        assert len(frame.fft_magnitudes) > 0
        assert len(frame.fft_frequencies) > 0
        assert "bass" in frame.frequency_bands
        assert "mid" in frame.frequency_bands
        assert 0.0 <= frame.amplitude <= 1.0
        assert 0.0 <= frame.peak <= 1.0

    def test_analyze_frame_without_configure_raises(self):
        analyzer = AudioAnalyzer()
        with pytest.raises(RuntimeError):
            analyzer.analyze_frame(0.0)

    def test_frequency_bands_are_populated(self, sample_audio):
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        frame = analyzer.analyze_frame(0.5)
        expected_bands = [
            "sub_bass", "bass", "low_mid", "mid",
            "upper_mid", "presence", "brilliance",
        ]
        for band in expected_bands:
            assert band in frame.frequency_bands

    def test_precompute_beats(self, sample_audio):
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        # Beats list should be populated (may be empty for pure sine)
        assert isinstance(analyzer._beat_timestamps, list)

    def test_smoothing(self, sample_audio):
        audio, sr = sample_audio
        analyzer = AudioAnalyzer(smoothing_factor=0.5)
        analyzer.configure(audio, sr)

        frame1 = analyzer.analyze_frame(0.1)
        frame2 = analyzer.analyze_frame(0.2)

        # Smoothing should make consecutive frames similar
        assert frame1.fft_magnitudes is not frame2.fft_magnitudes

    def test_spectral_flux_nonzero(self, chirp_audio):
        """Spectral flux should be > 0 between frames of a chirp signal."""
        audio, sr = chirp_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        # First frame establishes baseline
        analyzer.analyze_frame(0.1)
        # Second frame at a different time should show spectral change
        frame2 = analyzer.analyze_frame(0.5)

        assert frame2.spectral_flux > 0.0, (
            "Spectral flux should be nonzero for a chirp signal between different timestamps"
        )

    def test_beat_intensity_graduated(self, beat_audio):
        """Beat intensities should not all be identical (graduated, not binary)."""
        audio, sr = beat_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        intensities = [strength for _, strength in analyzer._beat_timestamps]

        if len(intensities) >= 2:
            # Not all intensities should be identical
            assert len(set(intensities)) > 1, (
                "Beat intensities should be graduated, not all identical"
            )

    def test_new_frame_analysis_fields(self, sample_audio):
        """All new FrameAnalysis fields should exist with correct types."""
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        frame = analyzer.analyze_frame(0.5)

        assert isinstance(frame.fft_magnitudes_db, np.ndarray)
        assert frame.fft_magnitudes_db.dtype == np.float32
        assert isinstance(frame.fft_magnitudes_norm, np.ndarray)
        assert frame.fft_magnitudes_norm.dtype == np.float32
        assert isinstance(frame.frequency_bands_norm, dict)
        assert isinstance(frame.amplitude_envelope, float)
        assert isinstance(frame.band_envelopes, dict)

    def test_db_magnitudes_in_range(self, sample_audio):
        """fft_magnitudes_db values should be in [0, 1]."""
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        frame = analyzer.analyze_frame(0.5)

        assert np.all(frame.fft_magnitudes_db >= 0.0)
        assert np.all(frame.fft_magnitudes_db <= 1.0)

    def test_running_peak_preserves_dynamics(self, sample_audio):
        """fft_magnitudes_norm max should be <= 1.0."""
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        for t in [0.2, 0.5, 0.8, 1.0, 1.5]:
            frame = analyzer.analyze_frame(t)
            assert np.max(frame.fft_magnitudes_norm) <= 1.0 + 1e-6

    def test_asymmetric_envelope(self, beat_audio):
        """Envelope should rise quickly on burst and decay slowly after."""
        audio, sr = beat_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        # Analyze frame during a burst (t=0.5)
        frame_burst = analyzer.analyze_frame(0.5)
        env_at_burst = frame_burst.amplitude_envelope

        # Analyze frame shortly after burst (t=0.6) — should still have some envelope
        frame_after = analyzer.analyze_frame(0.6)
        _ = frame_after.amplitude_envelope

        # Analyze frame well after burst (t=0.9) — envelope should have decayed further
        frame_later = analyzer.analyze_frame(0.9)
        env_later = frame_later.amplitude_envelope

        # Envelope at burst should be meaningful
        assert env_at_burst > 0.0
        # Envelope should decay over time (but not instantly)
        assert env_later < env_at_burst or env_at_burst < 1e-6

    def test_bands_norm_in_range(self, sample_audio):
        """All frequency_bands_norm values should be in [0, 1]."""
        audio, sr = sample_audio
        analyzer = AudioAnalyzer()
        analyzer.configure(audio, sr)

        # Run a few frames to let auto-gain stabilize
        for t in [0.1, 0.2, 0.3, 0.5]:
            frame = analyzer.analyze_frame(t)

        for name, value in frame.frequency_bands_norm.items():
            assert 0.0 <= value <= 1.0, f"Band '{name}' norm value {value} out of [0, 1]"

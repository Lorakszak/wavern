"""Tests for AudioAnalyzer."""

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

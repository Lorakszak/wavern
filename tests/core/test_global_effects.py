"""Tests for global post-processing effects intensity resolution.

WHAT THIS TESTS:
- _resolve_global_effect_intensity returns base intensity when audio disabled
- _resolve_global_effect_intensity returns modulated value when audio enabled
- _resolve_global_effect_intensity clamps result to [0.0, 1.0]
- _any_global_effect_enabled detects enabled effects
Does NOT test: shader compilation, FBO rendering, GUI
"""

import numpy as np
import pytest

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.renderer import (
    _any_global_effect_enabled,
    _resolve_global_effect_intensity,
)
from wavern.presets.schema import (
    AudioReactiveConfig,
    BloomEffect,
    ChromaticAberrationEffect,
    ColorShiftEffect,
    FilmGrainEffect,
    GlobalEffects,
    GlitchEffect,
    ScanlinesEffect,
    VignetteEffect,
)


def _make_frame(
    amplitude_envelope: float = 0.0,
    beat_intensity: float = 0.0,
    band_envelopes: dict[str, float] | None = None,
) -> FrameAnalysis:
    """Create a FrameAnalysis with controllable audio fields."""
    return FrameAnalysis(
        timestamp=1.0,
        waveform=np.zeros(2048, dtype=np.float32),
        fft_magnitudes=np.zeros(1024, dtype=np.float32),
        fft_frequencies=np.linspace(0, 22050, 1024, dtype=np.float32),
        frequency_bands={
            k: 0.0
            for k in (
                "sub_bass", "bass", "low_mid", "mid",
                "upper_mid", "presence", "brilliance",
            )
        },
        amplitude=0.0,
        peak=0.0,
        beat=False,
        beat_intensity=beat_intensity,
        spectral_centroid=0.0,
        spectral_flux=0.0,
        amplitude_envelope=amplitude_envelope,
        band_envelopes=band_envelopes or {},
    )


class TestResolveGlobalEffectIntensity:
    def test_manual_only(self):
        audio = AudioReactiveConfig()
        frame = _make_frame()
        assert _resolve_global_effect_intensity(0.7, audio, frame) == 0.7

    def test_audio_reactive(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0)
        frame = _make_frame(amplitude_envelope=0.8)
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == pytest.approx(0.5 * 0.8 * 1.0)

    def test_audio_reactive_with_sensitivity(self):
        audio = AudioReactiveConfig(enabled=True, source="bass", sensitivity=3.0)
        frame = _make_frame(band_envelopes={"bass": 0.6})
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == pytest.approx(0.5 * 0.6 * 3.0)

    def test_clamps_to_one(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=5.0)
        frame = _make_frame(amplitude_envelope=1.0)
        result = _resolve_global_effect_intensity(1.0, audio, frame)
        assert result == 1.0

    def test_clamps_to_zero(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0)
        frame = _make_frame(amplitude_envelope=0.0)
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == 0.0


class TestAnyGlobalEffectEnabled:
    def test_none_enabled(self):
        effects = GlobalEffects()
        assert _any_global_effect_enabled(effects) is False

    def test_vignette_enabled(self):
        effects = GlobalEffects(vignette=VignetteEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_chromatic_enabled(self):
        effects = GlobalEffects(
            chromatic_aberration=ChromaticAberrationEffect(enabled=True),
        )
        assert _any_global_effect_enabled(effects) is True

    def test_glitch_enabled(self):
        effects = GlobalEffects(glitch=GlitchEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_grain_enabled(self):
        effects = GlobalEffects(film_grain=FilmGrainEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_bloom_enabled(self):
        effects = GlobalEffects(bloom=BloomEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_scanlines_enabled(self):
        effects = GlobalEffects(scanlines=ScanlinesEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_color_shift_enabled(self):
        effects = GlobalEffects(color_shift=ColorShiftEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_multiple_enabled(self):
        effects = GlobalEffects(
            vignette=VignetteEffect(enabled=True),
            glitch=GlitchEffect(enabled=True),
        )
        assert _any_global_effect_enabled(effects) is True

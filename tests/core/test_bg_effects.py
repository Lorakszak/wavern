"""Tests for background effects audio-reactive intensity resolution.

WHAT THIS TESTS:
- AUDIO_SOURCE_MAP extracts correct FrameAnalysis fields
- _resolve_effect_intensity returns base intensity when audio disabled
- _resolve_effect_intensity returns modulated value when audio enabled
- _resolve_effect_intensity clamps result to [0.0, 1.0]
- _resolve_movement_intensity clamps to [0.0, 2.0]
- _any_bg_effect_enabled detects enabled effects
Does NOT test: shader compilation, FBO rendering, GUI
"""

import numpy as np
import pytest

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.renderer import (
    AUDIO_SOURCE_MAP,
    _any_bg_effect_enabled,
    _resolve_effect_intensity,
    _resolve_movement_intensity,
)
from wavern.presets.schema import (
    AudioReactiveConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
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


class TestAudioSourceMap:
    def test_amplitude_source(self):
        frame = _make_frame(amplitude_envelope=0.75)
        assert AUDIO_SOURCE_MAP["amplitude"](frame) == 0.75

    def test_bass_source(self):
        frame = _make_frame(band_envelopes={"bass": 0.6})
        assert AUDIO_SOURCE_MAP["bass"](frame) == 0.6

    def test_beat_source(self):
        frame = _make_frame(beat_intensity=0.9)
        assert AUDIO_SOURCE_MAP["beat"](frame) == 0.9

    def test_mid_source(self):
        frame = _make_frame(band_envelopes={"mid": 0.4})
        assert AUDIO_SOURCE_MAP["mid"](frame) == 0.4

    def test_treble_source(self):
        frame = _make_frame(band_envelopes={"brilliance": 0.3})
        assert AUDIO_SOURCE_MAP["treble"](frame) == 0.3

    def test_missing_band_defaults_zero(self):
        frame = _make_frame(band_envelopes={})
        assert AUDIO_SOURCE_MAP["bass"](frame) == 0.0

    def test_all_sources_present(self):
        assert set(AUDIO_SOURCE_MAP.keys()) == {"amplitude", "bass", "beat", "mid", "treble"}


class TestResolveEffectIntensity:
    def test_manual_only(self):
        effect = BackgroundEffect(enabled=True, intensity=0.7)
        frame = _make_frame()
        assert _resolve_effect_intensity(effect, frame) == 0.7

    def test_audio_reactive(self):
        effect = BackgroundEffect(
            enabled=True,
            intensity=0.5,
            audio=AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0),
        )
        frame = _make_frame(amplitude_envelope=0.8)
        result = _resolve_effect_intensity(effect, frame)
        assert result == pytest.approx(0.5 * 0.8 * 1.0)

    def test_audio_reactive_with_sensitivity(self):
        effect = BackgroundEffect(
            enabled=True,
            intensity=0.5,
            audio=AudioReactiveConfig(enabled=True, source="bass", sensitivity=3.0),
        )
        frame = _make_frame(band_envelopes={"bass": 0.6})
        result = _resolve_effect_intensity(effect, frame)
        assert result == pytest.approx(0.5 * 0.6 * 3.0)

    def test_clamps_to_one(self):
        effect = BackgroundEffect(
            enabled=True,
            intensity=1.0,
            audio=AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=5.0),
        )
        frame = _make_frame(amplitude_envelope=1.0)
        result = _resolve_effect_intensity(effect, frame)
        assert result == 1.0

    def test_clamps_to_zero(self):
        effect = BackgroundEffect(
            enabled=True,
            intensity=0.5,
            audio=AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0),
        )
        frame = _make_frame(amplitude_envelope=0.0)
        result = _resolve_effect_intensity(effect, frame)
        assert result == 0.0


class TestResolveMovementIntensity:
    def test_manual_only(self):
        movement = BackgroundMovement(type="shake", intensity=1.5)
        frame = _make_frame()
        assert _resolve_movement_intensity(movement, frame) == 1.5

    def test_audio_reactive(self):
        movement = BackgroundMovement(
            type="shake",
            intensity=1.0,
            audio=AudioReactiveConfig(enabled=True, source="beat", sensitivity=2.0),
        )
        frame = _make_frame(beat_intensity=0.8)
        result = _resolve_movement_intensity(movement, frame)
        assert result == pytest.approx(1.0 * 0.8 * 2.0)

    def test_clamps_to_two(self):
        movement = BackgroundMovement(
            type="shake",
            intensity=2.0,
            audio=AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=5.0),
        )
        frame = _make_frame(amplitude_envelope=1.0)
        result = _resolve_movement_intensity(movement, frame)
        assert result == 2.0


class TestAnyBgEffectEnabled:
    def test_none_enabled(self):
        effects = BackgroundEffects()
        assert _any_bg_effect_enabled(effects) is False

    def test_one_enabled(self):
        effects = BackgroundEffects(blur=BackgroundEffect(enabled=True))
        assert _any_bg_effect_enabled(effects) is True

    def test_pixelate_enabled(self):
        effects = BackgroundEffects(pixelate=BackgroundEffect(enabled=True))
        assert _any_bg_effect_enabled(effects) is True

    def test_posterize_enabled(self):
        effects = BackgroundEffects(posterize=BackgroundEffect(enabled=True))
        assert _any_bg_effect_enabled(effects) is True

    def test_invert_enabled(self):
        effects = BackgroundEffects(invert=BackgroundEffect(enabled=True))
        assert _any_bg_effect_enabled(effects) is True

    def test_multiple_enabled(self):
        effects = BackgroundEffects(
            blur=BackgroundEffect(enabled=True),
            brightness=BackgroundEffect(enabled=True),
        )
        assert _any_bg_effect_enabled(effects) is True

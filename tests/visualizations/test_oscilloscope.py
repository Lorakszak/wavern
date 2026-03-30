"""Tests for oscilloscope-specific logic.

WHAT THIS TESTS:
- _find_trigger_offset() locates zero-crossings correctly for rising, falling, and none modes
- Specific preset content: oscilloscope preset has solid background and rising trigger
Does NOT test: registration, PARAM_SCHEMA structure, generic preset validity (see test_common,
test_all_presets), OpenGL rendering, GPU initialization, or FBO persistence
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

_PRESET_DIR = Path(__file__).resolve().parents[2] / "src/wavern/presets/defaults"


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestOscilloscopeTrigger:
    """Tests for _find_trigger_offset static method."""

    @staticmethod
    def _trigger(waveform: list[float], mode: str) -> int:
        from wavern.visualizations.oscilloscope import OscilloscopeVisualization
        return OscilloscopeVisualization._find_trigger_offset(
            np.array(waveform, dtype="f4"), mode
        )

    def test_none_mode_returns_zero(self) -> None:
        waveform = [-0.5, -0.2, 0.1, 0.4, 0.2, -0.1]
        assert self._trigger(waveform, "none") == 0

    def test_rising_finds_zero_crossing(self) -> None:
        waveform = [-0.5, -0.1, 0.3, 0.6, 0.4, -0.2]
        result = self._trigger(waveform, "rising")
        assert result == 1

    def test_falling_finds_zero_crossing(self) -> None:
        waveform = [0.5, 0.2, 0.1, -0.3, -0.5, -0.2]
        result = self._trigger(waveform, "falling")
        assert result == 2

    def test_rising_no_crossing_returns_zero(self) -> None:
        waveform = [0.1, 0.2, 0.3, 0.4, 0.5] * 10
        assert self._trigger(waveform, "rising") == 0

    def test_falling_no_crossing_returns_zero(self) -> None:
        waveform = [-0.5, -0.4, -0.3, -0.2, -0.1] * 10
        assert self._trigger(waveform, "falling") == 0

    def test_empty_waveform_returns_zero(self) -> None:
        assert self._trigger([], "rising") == 0
        assert self._trigger([], "falling") == 0

    def test_single_sample_returns_zero(self) -> None:
        assert self._trigger([0.5], "rising") == 0

    def test_rising_searches_first_half_only(self) -> None:
        n = 100
        half = n // 2
        waveform = [0.5] * half + [-0.5, 0.5] + [0.5] * (half - 2)
        result = self._trigger(waveform, "rising")
        assert result == 0

    def test_exact_zero_sample_rising(self) -> None:
        waveform = [-0.2, 0.0, 0.4, 0.3]
        result = self._trigger(waveform, "rising")
        assert result == 1

    def test_falling_exact_zero_sample(self) -> None:
        waveform = [0.3, 0.0, -0.2, -0.4]
        result = self._trigger(waveform, "falling")
        assert result == 1


class TestOscilloscopePresetContent:
    """Tests for specific design-intent content in oscilloscope presets."""

    @staticmethod
    def _load(filename: str) -> dict:
        return json.loads((_PRESET_DIR / filename).read_text())

    def test_oscilloscope_has_solid_background(self) -> None:
        data = self._load("oscilloscope.json")
        assert data.get("background", {}).get("type") == "solid"

    def test_oscilloscope_has_rising_trigger(self) -> None:
        params = self._load("oscilloscope.json")["layers"][0].get("params", {})
        assert params.get("trigger_mode") == "rising"

    def test_oscilloscope_has_graticule(self) -> None:
        params = self._load("oscilloscope.json")["layers"][0].get("params", {})
        assert params.get("graticule_enabled") is True

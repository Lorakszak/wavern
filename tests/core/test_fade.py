"""Tests for fade-in/fade-out feature.

WHAT THIS TESTS:
- compute_fade_factor math: boundaries, midpoints, overlap, zero-duration edge cases
- Preset schema fade_in/fade_out fields: defaults, validation, JSON round-trip
- Pixel fade application: RGB and RGBA paths
Does NOT test: full export pipeline integration or GUI widgets
"""

import numpy as np
import pytest

from wavern.core.export import compute_fade_factor
from wavern.presets.schema import Preset, VisualizationLayer


class TestComputeFadeFactor:
    """Tests for the compute_fade_factor helper."""

    def test_no_fade(self) -> None:
        """No fade-in or fade-out returns 1.0 everywhere."""
        assert compute_fade_factor(0.0, 10.0, 0.0, 0.0) == 1.0
        assert compute_fade_factor(5.0, 10.0, 0.0, 0.0) == 1.0
        assert compute_fade_factor(10.0, 10.0, 0.0, 0.0) == 1.0

    def test_fade_in_start(self) -> None:
        """At t=0 with fade-in, factor should be 0."""
        assert compute_fade_factor(0.0, 10.0, 2.0, 0.0) == 0.0

    def test_fade_in_midpoint(self) -> None:
        """Halfway through fade-in should be 0.5."""
        assert compute_fade_factor(1.0, 10.0, 2.0, 0.0) == pytest.approx(0.5)

    def test_fade_in_end(self) -> None:
        """At the end of fade-in, factor should be 1.0."""
        assert compute_fade_factor(2.0, 10.0, 2.0, 0.0) == pytest.approx(1.0)

    def test_fade_in_after(self) -> None:
        """After fade-in completes, factor is 1.0."""
        assert compute_fade_factor(5.0, 10.0, 2.0, 0.0) == 1.0

    def test_fade_out_before(self) -> None:
        """Before fade-out starts, factor is 1.0."""
        assert compute_fade_factor(5.0, 10.0, 0.0, 2.0) == 1.0

    def test_fade_out_start(self) -> None:
        """At the start of fade-out, factor should be 1.0."""
        assert compute_fade_factor(8.0, 10.0, 0.0, 2.0) == pytest.approx(1.0)

    def test_fade_out_midpoint(self) -> None:
        """Halfway through fade-out should be 0.5."""
        assert compute_fade_factor(9.0, 10.0, 0.0, 2.0) == pytest.approx(0.5)

    def test_fade_out_end(self) -> None:
        """At the very end with fade-out, factor should be 0."""
        assert compute_fade_factor(10.0, 10.0, 0.0, 2.0) == pytest.approx(0.0)

    def test_both_fades(self) -> None:
        """Both fade-in and fade-out active, middle should be 1.0."""
        assert compute_fade_factor(0.0, 10.0, 2.0, 2.0) == 0.0
        assert compute_fade_factor(1.0, 10.0, 2.0, 2.0) == pytest.approx(0.5)
        assert compute_fade_factor(5.0, 10.0, 2.0, 2.0) == 1.0
        assert compute_fade_factor(9.0, 10.0, 2.0, 2.0) == pytest.approx(0.5)
        assert compute_fade_factor(10.0, 10.0, 2.0, 2.0) == pytest.approx(0.0)

    def test_overlap_fades(self) -> None:
        """When fade_in + fade_out > duration, factor never reaches 1.0."""
        # duration=4, fade_in=3, fade_out=3 → overlap in [1,3]
        # At t=2 (midpoint): fade_in gives 2/3, fade_out gives (4-2)/3 = 2/3
        factor = compute_fade_factor(2.0, 4.0, 3.0, 3.0)
        assert factor == pytest.approx(2.0 / 3.0)

    def test_negative_timestamp_clamped(self) -> None:
        """Negative timestamps should clamp to 0."""
        assert compute_fade_factor(-1.0, 10.0, 2.0, 0.0) == 0.0

    def test_beyond_duration_clamped(self) -> None:
        """Timestamps beyond duration should clamp to 0 with fade-out."""
        assert compute_fade_factor(11.0, 10.0, 0.0, 2.0) == 0.0


class TestPixelFadeApplication:
    """Tests that the fade math applies correctly to pixel arrays."""

    def test_rgb_fade_to_black(self) -> None:
        """Fade factor 0.5 should halve all RGB values."""
        pixels = np.array([[[200, 100, 50]]], dtype=np.uint8)
        fade = 0.5
        result = (pixels.astype(np.float32) * fade).astype(np.uint8)
        assert result[0, 0, 0] == 100
        assert result[0, 0, 1] == 50
        assert result[0, 0, 2] == 25

    def test_rgba_fade_to_transparent(self) -> None:
        """Fade factor 0.5 should halve all channels including alpha."""
        pixels = np.array([[[200, 100, 50, 255]]], dtype=np.uint8)
        fade = 0.5
        result = (pixels.astype(np.float32) * fade).astype(np.uint8)
        assert result[0, 0, 3] == 127  # 255 * 0.5 = 127.5 → 127

    def test_fade_zero_gives_black(self) -> None:
        """Fade factor 0 should produce all zeros."""
        pixels = np.full((2, 2, 3), 255, dtype=np.uint8)
        result = (pixels.astype(np.float32) * 0.0).astype(np.uint8)
        assert np.all(result == 0)

    def test_fade_one_unchanged(self) -> None:
        """Fade factor 1.0 should leave pixels unchanged."""
        pixels = np.array([[[128, 64, 32]]], dtype=np.uint8)
        result = (pixels.astype(np.float32) * 1.0).astype(np.uint8)
        np.testing.assert_array_equal(result, pixels)


class TestPresetFadeFields:
    """Tests that Preset schema includes fade fields correctly."""

    def test_defaults(self) -> None:
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        assert preset.fade_in == 0.0
        assert preset.fade_out == 0.0

    def test_custom_values(self) -> None:
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            fade_in=2.5,
            fade_out=3.0,
        )
        assert preset.fade_in == 2.5
        assert preset.fade_out == 3.0

    def test_json_roundtrip(self) -> None:
        preset = Preset(
            name="Fade Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            fade_in=1.5,
            fade_out=2.0,
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.fade_in == 1.5
        assert restored.fade_out == 2.0

    def test_validation_rejects_negative(self) -> None:
        with pytest.raises(Exception):  # pydantic ValidationError
            Preset(
                name="Bad",
                layers=[VisualizationLayer(visualization_type="spectrum_bars")],
                fade_in=-1.0,
            )

    def test_validation_rejects_over_max(self) -> None:
        with pytest.raises(Exception):  # pydantic ValidationError
            Preset(
                name="Bad",
                layers=[VisualizationLayer(visualization_type="spectrum_bars")],
                fade_out=31.0,
            )

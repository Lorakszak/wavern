"""Tests for wavern.visualizations.spectrum_bars height_reference parameter.

WHAT THIS TESTS:
- height_reference param exists in spectrum_bars PARAM_SCHEMA with correct type, default, and choices
- height_reference is absent from circular_spectrum and rect_spectrum schemas
- spectrum_bars default preset JSON contains height_reference set to "per_bar"
Does NOT test: rendering behaviour or visual output of the height_reference modes
"""

import json
from pathlib import Path

from wavern.visualizations.registry import VisualizationRegistry
import wavern.visualizations  # noqa: F401


PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "wavern" / "presets" / "defaults"


class TestHeightReferenceParam:
    """Verify height_reference exists only in spectrum_bars."""

    def test_exists_in_spectrum_bars(self) -> None:
        viz_cls = VisualizationRegistry().get("spectrum_bars")
        param = viz_cls.PARAM_SCHEMA["height_reference"]
        assert param["type"] == "choice"
        assert param["default"] == "per_bar"
        assert set(param["choices"]) == {"per_bar", "universal"}

    def test_absent_in_circular_spectrum(self) -> None:
        viz_cls = VisualizationRegistry().get("circular_spectrum")
        assert "height_reference" not in viz_cls.PARAM_SCHEMA

    def test_absent_in_rect_spectrum(self) -> None:
        viz_cls = VisualizationRegistry().get("rect_spectrum")
        assert "height_reference" not in viz_cls.PARAM_SCHEMA


class TestPresetDefaults:
    """Verify neon_spectrum preset JSON contains height_reference."""

    def test_spectrum_bars_preset(self) -> None:
        data = json.loads((PRESETS_DIR / "neon_spectrum.json").read_text())
        params = data["layers"][0]["params"]
        assert params["height_reference"] == "per_bar"

"""Tests for height_reference param on spectrum_bars visualization."""

import json
from pathlib import Path

from wavern.visualizations.registry import VisualizationRegistry
import wavern.visualizations  # noqa: F401


PRESETS_DIR = Path(__file__).resolve().parent.parent / "src" / "wavern" / "presets" / "defaults"


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
    """Verify spectrum_bars preset JSON contains height_reference."""

    def test_spectrum_bars_preset(self) -> None:
        data = json.loads((PRESETS_DIR / "spectrum_bars.json").read_text())
        params = data["visualization"]["params"]
        assert params["height_reference"] == "per_bar"

"""Tests for wavern.visualizations.lissajous.

WHAT THIS TESTS:
- LissajousVisualization is registered with correct NAME, DISPLAY_NAME, and CATEGORY
- PARAM_SCHEMA contains all required parameters with correct types and in-range defaults
- spin_speed allows negative values; symmetry, tail_fade, and waveform_smoothing have valid ranges
- The lissajous.json preset file loads against the Preset schema and all numeric params are in bounds
Does NOT test: OpenGL rendering or GPU initialization
"""

import json
from pathlib import Path

import pytest

from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestLissajousRegistration:
    def test_registered(self) -> None:
        registry = VisualizationRegistry()
        cls = registry.get("lissajous")
        assert cls.NAME == "lissajous"
        assert cls.DISPLAY_NAME == "Lissajous (Alpha)"
        assert cls.CATEGORY == "waveform"

    def test_in_list(self) -> None:
        registry = VisualizationRegistry()
        names = registry.list_names()
        assert "lissajous" in names


class TestLissajousParamSchema:
    def _schema(self) -> dict:
        from wavern.visualizations.lissajous import LissajousVisualization
        return LissajousVisualization.PARAM_SCHEMA

    def test_required_keys_present(self) -> None:
        schema = self._schema()
        for key in (
            "waveform_smoothing", "sample_count", "delay_samples",
            "amplitude_scale", "symmetry", "mirror_x", "spin_speed",
            "line_thickness", "glow_intensity", "tail_fade", "beat_reactive",
        ):
            assert key in schema, f"Missing param: {key}"

    def test_sample_count_type_and_range(self) -> None:
        sc = self._schema()["sample_count"]
        assert sc["type"] == "int"
        assert sc["min"] >= 1
        assert sc["max"] <= 512
        assert sc["min"] <= sc["default"] <= sc["max"]

    def test_delay_samples_type_and_range(self) -> None:
        ds = self._schema()["delay_samples"]
        assert ds["type"] == "int"
        assert ds["min"] == 0
        assert ds["min"] <= ds["default"] <= ds["max"]

    def test_transform_params_present(self) -> None:
        schema = self._schema()
        for key in ("offset_x", "offset_y", "scale", "rotation"):
            assert key in schema, f"Missing transform param: {key}"

    def test_beat_reactive_is_bool(self) -> None:
        assert self._schema()["beat_reactive"]["type"] == "bool"

    def test_waveform_smoothing_range(self) -> None:
        ws = self._schema()["waveform_smoothing"]
        assert ws["type"] == "int"
        assert ws["min"] >= 1
        assert ws["min"] <= ws["default"] <= ws["max"]

    def test_symmetry_range(self) -> None:
        sym = self._schema()["symmetry"]
        assert sym["type"] == "int"
        assert sym["min"] == 1
        assert sym["max"] <= 8
        assert sym["min"] <= sym["default"] <= sym["max"]

    def test_mirror_x_is_bool(self) -> None:
        assert self._schema()["mirror_x"]["type"] == "bool"

    def test_tail_fade_range(self) -> None:
        tf = self._schema()["tail_fade"]
        assert tf["type"] == "float"
        assert tf["min"] == 0.0
        assert tf["max"] == 1.0

    def test_spin_speed_allows_negative(self) -> None:
        ss = self._schema()["spin_speed"]
        assert ss["min"] < 0.0


class TestLissajousPreset:
    _PRESET_PATH = (
        Path(__file__).resolve().parents[2]
        / "src/wavern/presets/defaults/lissajous.json"
    )

    def test_preset_file_exists(self) -> None:
        assert self._PRESET_PATH.exists()

    def test_preset_loads_against_schema(self) -> None:
        raw = self._PRESET_PATH.read_text()
        preset = Preset.model_validate_json(raw)
        assert preset.visualization.visualization_type == "lissajous"

    def test_preset_params_within_schema_bounds(self) -> None:
        from wavern.visualizations.lissajous import LissajousVisualization

        raw = json.loads(self._PRESET_PATH.read_text())
        params = raw["visualization"].get("params", {})
        schema = LissajousVisualization.PARAM_SCHEMA

        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"{key}={value} out of range [{entry['min']}, {entry['max']}]"
                )

    def test_preset_color_palette_nonempty(self) -> None:
        raw = json.loads(self._PRESET_PATH.read_text())
        assert len(raw.get("color_palette", [])) >= 1

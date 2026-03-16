"""Tests for Radial Waveform visualization registration, schema, and preset."""

import json
from pathlib import Path

import pytest

from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestRadialWaveformRegistration:
    def test_registered(self) -> None:
        registry = VisualizationRegistry()
        cls = registry.get("radial_waveform")
        assert cls.NAME == "radial_waveform"
        assert cls.DISPLAY_NAME == "Radial Waveform"
        assert cls.CATEGORY == "waveform"

    def test_in_list(self) -> None:
        registry = VisualizationRegistry()
        names = registry.list_names()
        assert "radial_waveform" in names


class TestRadialWaveformParamSchema:
    def _schema(self) -> dict:
        from wavern.visualizations.radial_waveform import RadialWaveformVisualization
        return RadialWaveformVisualization.PARAM_SCHEMA

    def test_required_keys_present(self) -> None:
        schema = self._schema()
        for key in (
            "sample_count", "inner_radius", "wave_amplitude", "line_thickness",
            "smoothing", "filled", "rotation_speed", "rotation_direction",
            "mirror_mode", "glow_intensity",
        ):
            assert key in schema, f"Missing param: {key}"

    def test_sample_count_type_and_range(self) -> None:
        sc = self._schema()["sample_count"]
        assert sc["type"] == "int"
        assert sc["min"] >= 1
        assert sc["max"] <= 1024
        assert sc["min"] <= sc["default"] <= sc["max"]

    def test_inner_radius_range(self) -> None:
        ir = self._schema()["inner_radius"]
        assert ir["type"] == "float"
        assert ir["min"] <= ir["default"] <= ir["max"]

    def test_wave_amplitude_range(self) -> None:
        wa = self._schema()["wave_amplitude"]
        assert wa["type"] == "float"
        assert wa["min"] <= wa["default"] <= wa["max"]

    def test_smoothing_range(self) -> None:
        sm = self._schema()["smoothing"]
        assert sm["type"] == "int"
        assert sm["min"] >= 1
        assert sm["min"] <= sm["default"] <= sm["max"]

    def test_mirror_mode_choices(self) -> None:
        mm = self._schema()["mirror_mode"]
        assert mm["type"] == "choice"
        assert set(mm["choices"]) == {"none", "mirror", "duplicate"}
        assert mm["default"] in mm["choices"]

    def test_filled_is_bool(self) -> None:
        assert self._schema()["filled"]["type"] == "bool"

    def test_transform_params_present(self) -> None:
        schema = self._schema()
        for key in ("center_x", "center_y", "scale"):
            assert key in schema, f"Missing transform param: {key}"

    def test_image_params_present(self) -> None:
        schema = self._schema()
        for key in (
            "inner_image_path", "inner_image_padding",
            "inner_image_beat_bounce", "inner_image_bounce_strength",
        ):
            assert key in schema, f"Missing image param: {key}"

    def test_shape_beat_bounce_is_bool(self) -> None:
        assert self._schema()["shape_beat_bounce"]["type"] == "bool"


class TestRadialWaveformPreset:
    _PRESET_PATH = (
        Path(__file__).resolve().parents[1]
        / "src/wavern/presets/defaults/radial_waveform.json"
    )

    def test_preset_file_exists(self) -> None:
        assert self._PRESET_PATH.exists()

    def test_preset_loads_against_schema(self) -> None:
        raw = self._PRESET_PATH.read_text()
        preset = Preset.model_validate_json(raw)
        assert preset.visualization.visualization_type == "radial_waveform"

    def test_preset_params_within_schema_bounds(self) -> None:
        from wavern.visualizations.radial_waveform import RadialWaveformVisualization

        raw = json.loads(self._PRESET_PATH.read_text())
        params = raw["visualization"].get("params", {})
        schema = RadialWaveformVisualization.PARAM_SCHEMA

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

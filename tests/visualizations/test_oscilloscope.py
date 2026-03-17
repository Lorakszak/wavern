"""Tests for wavern.visualizations.oscilloscope.

WHAT THIS TESTS:
- OscilloscopeVisualization is registered with correct NAME, DISPLAY_NAME, and CATEGORY
- PARAM_SCHEMA contains all 24 required parameters with correct types and in-range defaults
- _find_trigger_offset() locates zero-crossings correctly for rising, falling, and none modes
- All 3 preset JSON files load against the Preset schema with params within PARAM_SCHEMA bounds

Does NOT test: OpenGL rendering, GPU initialization, or FBO persistence (requires GL context)
"""

import json
from pathlib import Path

import numpy as np
import pytest

from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry

_PRESET_DIR = Path(__file__).resolve().parents[2] / "src/wavern/presets/defaults"


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestOscilloscopeRegistration:
    def test_registered(self) -> None:
        registry = VisualizationRegistry()
        cls = registry.get("oscilloscope")
        assert cls.NAME == "oscilloscope"
        assert cls.DISPLAY_NAME == "CRT Oscilloscope (Beta)"
        assert cls.CATEGORY == "waveform"

    def test_in_list(self) -> None:
        registry = VisualizationRegistry()
        assert "oscilloscope" in registry.list_names()


class TestOscilloscopeParamSchema:
    @classmethod
    def _schema(cls) -> dict:
        from wavern.visualizations.oscilloscope import OscilloscopeVisualization
        return OscilloscopeVisualization.PARAM_SCHEMA

    def test_all_required_keys_present(self) -> None:
        schema = self._schema()
        required = {
            # Trace
            "display_mode", "line_thickness", "sample_count",
            "amplitude_scale", "wave_range", "trigger_mode",
            # Phosphor
            "phosphor_glow", "glow_radius", "phosphor_persistence",
            # CRT Effects
            "barrel_distortion", "scanline_intensity", "scanline_count",
            "chromatic_aberration", "vignette", "noise_intensity",
            # Screen
            "screen_flicker", "screen_tint",
            "graticule_enabled", "graticule_intensity", "graticule_divisions",
            "bezel",
            # Transform
            "offset_x", "offset_y", "scale", "rotation",
        }
        missing = required - set(schema.keys())
        assert not missing, f"Missing params: {missing}"

    def test_float_params_have_valid_ranges(self) -> None:
        schema = self._schema()
        float_params = [k for k, v in schema.items() if v["type"] == "float"]
        for key in float_params:
            entry = schema[key]
            assert entry["min"] <= entry["default"] <= entry["max"], (
                f"{key}: default {entry['default']} not in [{entry['min']}, {entry['max']}]"
            )

    def test_int_params_have_valid_ranges(self) -> None:
        schema = self._schema()
        int_params = [k for k, v in schema.items() if v["type"] == "int"]
        for key in int_params:
            entry = schema[key]
            assert entry["min"] <= entry["default"] <= entry["max"], (
                f"{key}: default {entry['default']} not in [{entry['min']}, {entry['max']}]"
            )

    def test_bool_params(self) -> None:
        schema = self._schema()
        for key in ("graticule_enabled", "bezel"):
            assert schema[key]["type"] == "bool"
            assert isinstance(schema[key]["default"], bool)

    def test_choice_params_have_options(self) -> None:
        schema = self._schema()
        for key in ("display_mode", "trigger_mode"):
            assert schema[key]["type"] == "str"
            assert "options" in schema[key]
            assert schema[key]["default"] in schema[key]["options"]

    def test_display_mode_options(self) -> None:
        opts = self._schema()["display_mode"]["options"]
        assert set(opts) == {"line", "dot", "filled"}

    def test_trigger_mode_options(self) -> None:
        opts = self._schema()["trigger_mode"]["options"]
        assert set(opts) == {"none", "rising", "falling"}

    def test_phosphor_persistence_range(self) -> None:
        entry = self._schema()["phosphor_persistence"]
        assert entry["type"] == "float"
        assert entry["min"] == 0.0
        assert entry["max"] == 0.95
        assert entry["default"] == 0.0

    def test_sample_count_range(self) -> None:
        entry = self._schema()["sample_count"]
        assert entry["type"] == "int"
        assert entry["min"] == 64
        assert entry["max"] == 2048

    def test_transform_params_present(self) -> None:
        schema = self._schema()
        for key in ("offset_x", "offset_y", "scale", "rotation"):
            assert key in schema

    def test_rotation_full_range(self) -> None:
        rot = self._schema()["rotation"]
        assert rot["min"] == -180.0
        assert rot["max"] == 180.0

    def test_fill_screen_is_bool_default_false(self) -> None:
        entry = self._schema()["fill_screen"]
        assert entry["type"] == "bool"
        assert entry["default"] is False


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
        # Crosses zero between index 1 and 2
        waveform = [-0.5, -0.1, 0.3, 0.6, 0.4, -0.2]
        result = self._trigger(waveform, "rising")
        assert result == 1

    def test_falling_finds_zero_crossing(self) -> None:
        # Crosses zero downward between index 2 and 3
        waveform = [0.5, 0.2, 0.1, -0.3, -0.5, -0.2]
        result = self._trigger(waveform, "falling")
        assert result == 2

    def test_rising_no_crossing_returns_zero(self) -> None:
        # All positive, no rising crossing through zero
        waveform = [0.1, 0.2, 0.3, 0.4, 0.5] * 10
        assert self._trigger(waveform, "rising") == 0

    def test_falling_no_crossing_returns_zero(self) -> None:
        # All negative, no falling crossing through zero
        waveform = [-0.5, -0.4, -0.3, -0.2, -0.1] * 10
        assert self._trigger(waveform, "falling") == 0

    def test_empty_waveform_returns_zero(self) -> None:
        assert self._trigger([], "rising") == 0
        assert self._trigger([], "falling") == 0

    def test_single_sample_returns_zero(self) -> None:
        assert self._trigger([0.5], "rising") == 0

    def test_rising_searches_first_half_only(self) -> None:
        # Put a rising crossing only in the second half — should return 0
        n = 100
        half = n // 2
        waveform = [0.5] * half + [-0.5, 0.5] + [0.5] * (half - 2)
        result = self._trigger(waveform, "rising")
        # The crossing is at index `half`, outside search window
        assert result == 0

    def test_exact_zero_sample_rising(self) -> None:
        # Waveform[i] == 0.0 exactly — still a valid rising crossing if next > 0
        waveform = [-0.2, 0.0, 0.4, 0.3]
        result = self._trigger(waveform, "rising")
        assert result == 1  # index 1: waveform[1]=0 <= 0 < waveform[2]=0.4

    def test_falling_exact_zero_sample(self) -> None:
        waveform = [0.3, 0.0, -0.2, -0.4]
        result = self._trigger(waveform, "falling")
        assert result == 1  # index 1: waveform[1]=0 >= 0 > waveform[2]=-0.2


class TestOscilloscopePresets:
    """Validate all 3 oscilloscope preset JSON files."""

    @staticmethod
    def _load_preset(filename: str) -> tuple[Preset, dict]:
        path = _PRESET_DIR / filename
        assert path.exists(), f"Preset file not found: {path}"
        raw = path.read_text()
        preset = Preset.model_validate_json(raw)
        data = json.loads(raw)
        return preset, data

    @staticmethod
    def _check_params_in_bounds(params: dict, schema: dict, preset_name: str) -> None:
        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"[{preset_name}] {key}={value} out of range [{entry['min']}, {entry['max']}]"
                )

    def test_green_phosphor_loads(self) -> None:
        preset, _ = self._load_preset("oscilloscope_green_phosphor.json")
        assert preset.visualization.visualization_type == "oscilloscope"
        assert preset.name == "Green Phosphor Scope"

    def test_green_phosphor_params_in_bounds(self) -> None:
        from wavern.visualizations.oscilloscope import OscilloscopeVisualization
        _, data = self._load_preset("oscilloscope_green_phosphor.json")
        self._check_params_in_bounds(
            data["visualization"].get("params", {}),
            OscilloscopeVisualization.PARAM_SCHEMA,
            "green_phosphor",
        )

    def test_green_phosphor_color_palette(self) -> None:
        _, data = self._load_preset("oscilloscope_green_phosphor.json")
        assert len(data.get("color_palette", [])) >= 1

    def test_neon_loads(self) -> None:
        preset, _ = self._load_preset("oscilloscope_neon.json")
        assert preset.visualization.visualization_type == "oscilloscope"
        assert preset.name == "Neon Scope"

    def test_neon_params_in_bounds(self) -> None:
        from wavern.visualizations.oscilloscope import OscilloscopeVisualization
        _, data = self._load_preset("oscilloscope_neon.json")
        self._check_params_in_bounds(
            data["visualization"].get("params", {}),
            OscilloscopeVisualization.PARAM_SCHEMA,
            "neon",
        )

    def test_busted_crt_loads(self) -> None:
        preset, _ = self._load_preset("oscilloscope_busted_crt.json")
        assert preset.visualization.visualization_type == "oscilloscope"
        assert preset.name == "Busted CRT"

    def test_busted_crt_params_in_bounds(self) -> None:
        from wavern.visualizations.oscilloscope import OscilloscopeVisualization
        _, data = self._load_preset("oscilloscope_busted_crt.json")
        self._check_params_in_bounds(
            data["visualization"].get("params", {}),
            OscilloscopeVisualization.PARAM_SCHEMA,
            "busted_crt",
        )

    def test_busted_crt_has_persistence(self) -> None:
        _, data = self._load_preset("oscilloscope_busted_crt.json")
        params = data["visualization"].get("params", {})
        assert params.get("phosphor_persistence", 0.0) > 0.0

    def test_busted_crt_dot_mode(self) -> None:
        _, data = self._load_preset("oscilloscope_busted_crt.json")
        params = data["visualization"].get("params", {})
        assert params.get("display_mode") == "dot"

    def test_all_presets_have_solid_background(self) -> None:
        for filename in (
            "oscilloscope_green_phosphor.json",
            "oscilloscope_neon.json",
            "oscilloscope_busted_crt.json",
        ):
            _, data = self._load_preset(filename)
            assert data.get("background", {}).get("type") == "solid", (
                f"{filename}: expected solid background"
            )

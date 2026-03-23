"""Tests for wavern.visualizations.tunnel.

WHAT THIS TESTS:
- TunnelVisualization is registered with correct NAME, DISPLAY_NAME, and CATEGORY
- PARAM_SCHEMA contains all required parameters with correct types and in-range defaults
- direction and ring_shape params have correct choice options
- All three preset JSON files (tunnel_warp, tunnel_vortex, tunnel_emergence) load against
  the Preset schema and all numeric params are within PARAM_SCHEMA bounds
Does NOT test: OpenGL rendering or GPU initialization
"""

import json
from pathlib import Path

import pytest

from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry

_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "src/wavern/presets/defaults"


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestTunnelRegistration:
    def test_registered(self) -> None:
        registry = VisualizationRegistry()
        cls = registry.get("tunnel")
        assert cls.NAME == "tunnel"
        assert cls.DISPLAY_NAME == "Tunnel (Alpha)"
        assert cls.CATEGORY == "abstract"

    def test_in_list(self) -> None:
        registry = VisualizationRegistry()
        assert "tunnel" in registry.list_names()


class TestTunnelParamSchema:
    def _schema(self) -> dict:
        from wavern.visualizations.tunnel import TunnelVisualization
        return TunnelVisualization.PARAM_SCHEMA

    def test_all_params_present(self) -> None:
        schema = self._schema()
        expected = [
            "ring_count", "direction", "base_speed", "bass_drive", "beat_burst",
            "ring_thickness", "ring_gap", "spiral_twist", "perspective", "depth_fade",
            "color_cycle_speed", "color_spread", "glow_intensity", "pulse_intensity",
            "ring_shape", "center_x", "center_y", "scale", "rotation",
        ]
        for key in expected:
            assert key in schema, f"Missing param: {key}"

    def test_ring_count_type_and_range(self) -> None:
        p = self._schema()["ring_count"]
        assert p["type"] == "int"
        assert p["min"] == 4
        assert p["max"] == 64
        assert p["min"] <= p["default"] <= p["max"]

    def test_direction_choices(self) -> None:
        p = self._schema()["direction"]
        assert p["type"] == "choice"
        assert set(p["choices"]) == {"inward", "outward"}
        assert p["default"] in p["choices"]

    def test_ring_shape_choices(self) -> None:
        p = self._schema()["ring_shape"]
        assert p["type"] == "choice"
        assert set(p["choices"]) == {"circle", "square", "hexagon", "octagon"}
        assert p["default"] in p["choices"]

    def test_spiral_twist_allows_negative(self) -> None:
        p = self._schema()["spiral_twist"]
        assert p["type"] == "int"
        assert p["min"] < 0
        assert p["max"] > 0

    def test_all_float_int_defaults_in_range(self) -> None:
        schema = self._schema()
        for name, p in schema.items():
            if p["type"] in ("int", "float"):
                assert p["min"] <= p["default"] <= p["max"], (
                    f"{name}: default {p['default']} not in [{p['min']}, {p['max']}]"
                )

    def test_center_xy_range(self) -> None:
        schema = self._schema()
        for key in ("center_x", "center_y"):
            p = schema[key]
            assert p["min"] == -1.0
            assert p["max"] == 1.0

    def test_rotation_range(self) -> None:
        p = self._schema()["rotation"]
        assert p["min"] == -180.0
        assert p["max"] == 180.0


class _PresetTestBase:
    """Shared preset validation logic."""

    preset_file: str
    expected_viz_type: str = "tunnel"

    @property
    def _path(self) -> Path:
        return _DEFAULTS_DIR / self.preset_file

    def test_file_exists(self) -> None:
        assert self._path.exists(), f"{self.preset_file} not found"

    def test_loads_against_schema(self) -> None:
        preset = Preset.model_validate_json(self._path.read_text())
        assert preset.visualization.visualization_type == self.expected_viz_type

    def test_params_within_bounds(self) -> None:
        from wavern.visualizations.tunnel import TunnelVisualization

        raw = json.loads(self._path.read_text())
        params = raw["visualization"].get("params", {})
        schema = TunnelVisualization.PARAM_SCHEMA

        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"{self.preset_file}: {key}={value} out of [{entry['min']}, {entry['max']}]"
                )

    def test_color_palette_nonempty(self) -> None:
        raw = json.loads(self._path.read_text())
        assert len(raw.get("color_palette", [])) >= 1


class TestTunnelWarpPreset(_PresetTestBase):
    preset_file = "tunnel_warp.json"

    def test_is_inward(self) -> None:
        raw = json.loads(self._path.read_text())
        assert raw["visualization"]["params"]["direction"] == "inward"


class TestTunnelVortexPreset(_PresetTestBase):
    preset_file = "tunnel_vortex.json"

    def test_has_spiral_twist(self) -> None:
        raw = json.loads(self._path.read_text())
        assert raw["visualization"]["params"]["spiral_twist"] != 0.0

    def test_is_hexagon(self) -> None:
        raw = json.loads(self._path.read_text())
        assert raw["visualization"]["params"]["ring_shape"] == "hexagon"


class TestTunnelEmergencePreset(_PresetTestBase):
    preset_file = "tunnel_emergence.json"

    def test_is_outward(self) -> None:
        raw = json.loads(self._path.read_text())
        assert raw["visualization"]["params"]["direction"] == "outward"

    def test_is_octagon(self) -> None:
        raw = json.loads(self._path.read_text())
        assert raw["visualization"]["params"]["ring_shape"] == "octagon"

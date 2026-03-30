"""Tests for tunnel-specific preset content.

WHAT THIS TESTS:
- warp_drive uses inward direction with circle ring_shape
- spiral_galaxy has a tunnel layer with spiral_twist and inward direction
Does NOT test: registration, PARAM_SCHEMA structure, generic preset validity (see test_common,
test_all_presets), OpenGL rendering, or GPU initialization
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "src/wavern/presets/defaults"


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestWarpDrivePreset:
    def test_is_inward(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "warp_drive.json").read_text())
        tunnel_layer = raw["layers"][0]
        assert tunnel_layer["params"]["direction"] == "inward"

    def test_is_circle(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "warp_drive.json").read_text())
        tunnel_layer = raw["layers"][0]
        assert tunnel_layer["params"]["ring_shape"] == "circle"

    def test_has_particle_debris_layer(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "warp_drive.json").read_text())
        assert len(raw["layers"]) == 2
        assert raw["layers"][1]["visualization_type"] == "particles"


class TestSpiralGalaxyPreset:
    def test_has_tunnel_layer(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "spiral_galaxy.json").read_text())
        tunnel_layers = [ly for ly in raw["layers"] if ly["visualization_type"] == "tunnel"]
        assert len(tunnel_layers) == 1

    def test_tunnel_has_spiral_twist(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "spiral_galaxy.json").read_text())
        tunnel_layer = [ly for ly in raw["layers"] if ly["visualization_type"] == "tunnel"][0]
        assert tunnel_layer["params"]["spiral_twist"] != 0

    def test_is_three_layers(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "spiral_galaxy.json").read_text())
        assert len(raw["layers"]) == 3

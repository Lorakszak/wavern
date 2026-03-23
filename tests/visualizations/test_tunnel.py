"""Tests for tunnel-specific preset content.

WHAT THIS TESTS:
- tunnel_warp uses inward direction
- tunnel_vortex has non-zero spiral_twist and hexagon ring_shape
- tunnel_emergence uses outward direction and octagon ring_shape
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


class TestTunnelWarpPreset:
    def test_is_inward(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "tunnel_warp.json").read_text())
        assert raw["visualization"]["params"]["direction"] == "inward"


class TestTunnelVortexPreset:
    def test_has_spiral_twist(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "tunnel_vortex.json").read_text())
        assert raw["visualization"]["params"]["spiral_twist"] != 0.0

    def test_is_hexagon(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "tunnel_vortex.json").read_text())
        assert raw["visualization"]["params"]["ring_shape"] == "hexagon"


class TestTunnelEmergencePreset:
    def test_is_outward(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "tunnel_emergence.json").read_text())
        assert raw["visualization"]["params"]["direction"] == "outward"

    def test_is_octagon(self) -> None:
        raw = json.loads((_DEFAULTS_DIR / "tunnel_emergence.json").read_text())
        assert raw["visualization"]["params"]["ring_shape"] == "octagon"

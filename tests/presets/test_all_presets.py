"""Auto-discovered validation tests for ALL built-in preset JSON files.

WHAT THIS TESTS:
- Every JSON file in presets/defaults/ loads against the Preset pydantic schema
- Each preset's visualization_type matches a registered visualization
- All numeric params are within the PARAM_SCHEMA bounds for their visualization
- Every preset has at least one color_palette entry
Does NOT test: PresetManager file I/O, schema model internals, or visualization rendering
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wavern.presets.schema import Preset, VisualizationLayer
from wavern.visualizations.registry import VisualizationRegistry

# Ensure all built-in visualizations are registered
import wavern.visualizations  # noqa: F401

_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "src/wavern/presets/defaults"
_ALL_PRESETS = sorted(_DEFAULTS_DIR.glob("*.json"))
_registry = VisualizationRegistry()


@pytest.fixture(params=_ALL_PRESETS, ids=[p.name for p in _ALL_PRESETS])
def preset_path(request: pytest.FixtureRequest) -> Path:
    """Yield each preset JSON file path."""
    return request.param


class TestPresetValidity:
    """Every preset file passes structural validation."""

    def test_loads_against_schema(self, preset_path: Path) -> None:
        Preset.model_validate_json(preset_path.read_text())

    def test_visualization_type_registered(self, preset_path: Path) -> None:
        preset = Preset.model_validate_json(preset_path.read_text())
        layer: VisualizationLayer = preset.layers[0]
        viz_type = layer.visualization_type
        assert viz_type in _registry.list_names(), (
            f"{preset_path.name}: unknown visualization_type {viz_type!r}"
        )

    def test_params_within_schema_bounds(self, preset_path: Path) -> None:
        raw = json.loads(preset_path.read_text())
        viz_type = raw["layers"][0]["visualization_type"]
        params = raw["layers"][0].get("params", {})
        schema = _registry.get(viz_type).PARAM_SCHEMA

        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"{preset_path.name}: {key}={value} "
                    f"out of [{entry['min']}, {entry['max']}]"
                )

    def test_color_palette_nonempty(self, preset_path: Path) -> None:
        raw = json.loads(preset_path.read_text())
        assert len(raw.get("color_palette", [])) >= 1, (
            f"{preset_path.name}: color_palette must have at least one entry"
        )

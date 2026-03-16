"""Tests for showcase presets (12 original + 7 new replacements)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wavern.presets.schema import Preset

DEFAULTS_DIR = Path(__file__).resolve().parents[1] / "src/wavern/presets/defaults"

# (filename, visualization_type, visualization_import_path, class_name)
NEW_PRESETS = [
    # --- 5 kept non-beta presets ---
    ("cyberpunk_skyline.json", "spectrum_bars", "wavern.visualizations.spectrum_bars", "SpectrumBarsVisualization"),
    ("mirror_cathedral.json", "spectrum_bars", "wavern.visualizations.spectrum_bars", "SpectrumBarsVisualization"),
    ("deep_ocean_pulse.json", "circular_spectrum", "wavern.visualizations.circular_spectrum", "CircularSpectrumVisualization"),
    ("solar_corona.json", "circular_spectrum", "wavern.visualizations.circular_spectrum", "CircularSpectrumVisualization"),
    ("neon_fortress.json", "rect_spectrum", "wavern.visualizations.rect_spectrum", "RectSpectrumVisualization"),
    # --- 7 beta-marked presets ---
    ("neon_flood.json", "waveform", "wavern.visualizations.waveform", "WaveformVisualization"),
    ("oscilloscope.json", "waveform", "wavern.visualizations.waveform", "WaveformVisualization"),
    ("stardust_rain.json", "particles", "wavern.visualizations.particles", "ParticlesVisualization"),
    ("volcanic_eruption.json", "particles", "wavern.visualizations.particles", "ParticlesVisualization"),
    ("aurora_borealis.json", "smoky_waves", "wavern.visualizations.smoky_waves", "SmokyWavesVisualization"),
    ("kaleidoscope.json", "lissajous", "wavern.visualizations.lissajous", "LissajousVisualization"),
    ("ghost_signal.json", "lissajous", "wavern.visualizations.lissajous", "LissajousVisualization"),
    # --- 7 new replacement presets ---
    ("shadow_cascade.json", "spectrum_bars", "wavern.visualizations.spectrum_bars", "SpectrumBarsVisualization"),
    ("vertical_rainfall.json", "spectrum_bars", "wavern.visualizations.spectrum_bars", "SpectrumBarsVisualization"),
    ("bouncing_orbit.json", "circular_spectrum", "wavern.visualizations.circular_spectrum", "CircularSpectrumVisualization"),
    ("shadow_halo.json", "circular_spectrum", "wavern.visualizations.circular_spectrum", "CircularSpectrumVisualization"),
    ("reverse_vortex.json", "circular_spectrum", "wavern.visualizations.circular_spectrum", "CircularSpectrumVisualization"),
    ("pulsing_cage.json", "rect_spectrum", "wavern.visualizations.rect_spectrum", "RectSpectrumVisualization"),
    ("shadow_monolith.json", "rect_spectrum", "wavern.visualizations.rect_spectrum", "RectSpectrumVisualization"),
]


@pytest.fixture(params=NEW_PRESETS, ids=[p[0] for p in NEW_PRESETS])
def preset_info(request: pytest.FixtureRequest) -> tuple[str, str, str, str]:
    """Yield (filename, viz_type, module_path, class_name) for each new preset."""
    return request.param


class TestNewPresets:
    """Validate all 19 showcase presets."""

    def test_preset_file_exists(self, preset_info: tuple[str, str, str, str]) -> None:
        filename = preset_info[0]
        path = DEFAULTS_DIR / filename
        assert path.exists(), f"{filename} not found in {DEFAULTS_DIR}"

    def test_preset_loads_against_schema(self, preset_info: tuple[str, str, str, str]) -> None:
        filename, viz_type, _, _ = preset_info
        raw = (DEFAULTS_DIR / filename).read_text()
        preset = Preset.model_validate_json(raw)
        assert preset.visualization.visualization_type == viz_type

    def test_preset_params_within_schema_bounds(self, preset_info: tuple[str, str, str, str]) -> None:
        import importlib

        filename, _, module_path, class_name = preset_info
        module = importlib.import_module(module_path)
        viz_class = getattr(module, class_name)

        raw = json.loads((DEFAULTS_DIR / filename).read_text())
        params = raw["visualization"].get("params", {})
        schema = viz_class.PARAM_SCHEMA

        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"{filename}: {key}={value} out of range "
                    f"[{entry['min']}, {entry['max']}]"
                )

    def test_preset_color_palette_nonempty(self, preset_info: tuple[str, str, str, str]) -> None:
        filename = preset_info[0]
        raw = json.loads((DEFAULTS_DIR / filename).read_text())
        assert len(raw.get("color_palette", [])) >= 1, (
            f"{filename}: color_palette must have at least one entry"
        )

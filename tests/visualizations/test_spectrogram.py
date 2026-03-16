"""Tests for wavern.visualizations.spectrogram.

WHAT THIS TESTS:
- SpectrogramVisualization is registered with correct NAME, DISPLAY_NAME, and CATEGORY
- PARAM_SCHEMA contains all required parameters with correct choice sets and numeric ranges
- _resample_spectrum() produces float32 output of the requested length for linear, log, and mel scales
- The spectrogram.json preset loads against the Preset schema and numeric params are in bounds
Does NOT test: OpenGL rendering, GPU texture upload, or scrolling animation
"""

import json
from pathlib import Path

import numpy as np
import pytest

from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry


@pytest.fixture(autouse=True)
def _register() -> None:
    import wavern.visualizations  # noqa: F401


class TestSpectrogramRegistration:
    def test_registered(self) -> None:
        registry = VisualizationRegistry()
        cls = registry.get("spectrogram")
        assert cls.NAME == "spectrogram"
        assert cls.DISPLAY_NAME == "Spectrogram (Alpha)"
        assert cls.CATEGORY == "spectrum"

    def test_in_list(self) -> None:
        registry = VisualizationRegistry()
        assert "spectrogram" in registry.list_names()


class TestSpectrogramParamSchema:
    def _schema(self) -> dict:
        from wavern.visualizations.spectrogram import SpectrogramVisualization
        return SpectrogramVisualization.PARAM_SCHEMA

    def test_required_keys_present(self) -> None:
        schema = self._schema()
        for key in (
            "scroll_direction", "scroll_speed", "frequency_scale",
            "frequency_limit", "min_frequency", "max_frequency",
            "color_map", "brightness", "contrast", "saturation",
            "history_length", "blur", "bar_separation",
        ):
            assert key in schema, f"Missing param: {key}"

    def test_scroll_direction_choices(self) -> None:
        sd = self._schema()["scroll_direction"]
        assert sd["type"] == "choice"
        assert set(sd["choices"]) == {"left", "right", "up", "down"}
        assert sd["default"] in sd["choices"]

    def test_color_map_choices(self) -> None:
        cm = self._schema()["color_map"]
        assert cm["type"] == "choice"
        assert set(cm["choices"]) == {"palette", "inferno", "magma", "viridis", "plasma", "grayscale"}

    def test_frequency_scale_choices(self) -> None:
        fs = self._schema()["frequency_scale"]
        assert fs["type"] == "choice"
        assert set(fs["choices"]) == {"linear", "logarithmic", "mel"}

    def test_scroll_speed_range(self) -> None:
        ss = self._schema()["scroll_speed"]
        assert ss["type"] == "float"
        assert ss["min"] <= ss["default"] <= ss["max"]

    def test_history_length_range(self) -> None:
        hl = self._schema()["history_length"]
        assert hl["type"] == "int"
        assert hl["min"] >= 64
        assert hl["max"] <= 1024
        assert hl["min"] <= hl["default"] <= hl["max"]

    def test_min_frequency_range(self) -> None:
        mf = self._schema()["min_frequency"]
        assert mf["type"] == "int"
        assert mf["min"] == 20
        assert mf["min"] <= mf["default"] <= mf["max"]

    def test_blur_range(self) -> None:
        bl = self._schema()["blur"]
        assert bl["type"] == "float"
        assert bl["min"] == 0.0
        assert bl["min"] <= bl["default"] <= bl["max"]

    def test_bar_separation_is_bool(self) -> None:
        assert self._schema()["bar_separation"]["type"] == "bool"

    def test_frequency_limit_is_bool(self) -> None:
        assert self._schema()["frequency_limit"]["type"] == "bool"

    def test_transform_params_present(self) -> None:
        schema = self._schema()
        for key in ("offset_x", "offset_y", "scale"):
            assert key in schema, f"Missing transform param: {key}"


class TestSpectrogramResample:
    def test_resample_linear_output_length(self) -> None:
        from wavern.visualizations.spectrogram import _resample_spectrum
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "linear", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_logarithmic_output_length(self) -> None:
        from wavern.visualizations.spectrogram import _resample_spectrum
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "logarithmic", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_mel_output_length(self) -> None:
        from wavern.visualizations.spectrogram import _resample_spectrum
        mags = np.random.rand(512).astype("f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "mel", 20.0, 16000.0)
        assert len(out) == 256

    def test_resample_dtype(self) -> None:
        from wavern.visualizations.spectrogram import _resample_spectrum
        mags = np.ones(512, dtype="f4")
        freqs = np.linspace(0, 22050, 512).astype("f4")
        out = _resample_spectrum(mags, freqs, 256, "linear", 20.0, 16000.0)
        assert out.dtype == np.float32


class TestSpectrogramPreset:
    _PRESET_PATH = (
        Path(__file__).resolve().parents[2]
        / "src/wavern/presets/defaults/spectrogram.json"
    )

    def test_preset_file_exists(self) -> None:
        assert self._PRESET_PATH.exists()

    def test_preset_loads_against_schema(self) -> None:
        preset = Preset.model_validate_json(self._PRESET_PATH.read_text())
        assert preset.visualization.visualization_type == "spectrogram"

    def test_preset_params_within_schema_bounds(self) -> None:
        from wavern.visualizations.spectrogram import SpectrogramVisualization

        raw = json.loads(self._PRESET_PATH.read_text())
        params = raw["visualization"].get("params", {})
        schema = SpectrogramVisualization.PARAM_SCHEMA

        for key, value in params.items():
            if key not in schema:
                continue
            entry = schema[key]
            if entry["type"] in ("int", "float"):
                assert entry["min"] <= value <= entry["max"], (
                    f"{key}={value} out of [{entry['min']}, {entry['max']}]"
                )

    def test_preset_color_palette_nonempty(self) -> None:
        raw = json.loads(self._PRESET_PATH.read_text())
        assert len(raw.get("color_palette", [])) >= 1

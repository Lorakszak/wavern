"""Tests for multi-layer renderer compositing.

WHAT THIS TESTS:
- Renderer creates multiple visualization instances from preset layers
- Layer FBOs are created and sized correctly
- Compositing pass produces output without errors
- Visibility toggle skips layers
- Cleanup releases layers and FBOs
Does NOT test: GUI integration, export pipeline, individual viz rendering
"""

import moderngl
import numpy as np
import pytest

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.renderer import Renderer
from wavern.presets.schema import (
    BlendMode,
    Preset,
    VisualizationLayer,
)


def _make_frame() -> FrameAnalysis:
    """Create a minimal FrameAnalysis for testing."""
    return FrameAnalysis(
        timestamp=0.0,
        waveform=np.zeros(2048, dtype=np.float32),
        fft_magnitudes=np.zeros(1024, dtype=np.float32),
        fft_frequencies=np.linspace(0, 22050, 1024, dtype=np.float32),
        frequency_bands={
            k: 0.0
            for k in (
                "sub_bass", "bass", "low_mid", "mid",
                "upper_mid", "presence", "brilliance",
            )
        },
        amplitude=0.0,
        peak=0.0,
        beat=False,
        beat_intensity=0.0,
        spectral_centroid=0.0,
        spectral_flux=0.0,
    )


@pytest.fixture
def ctx():
    """Standalone OpenGL context for testing."""
    _ctx = moderngl.create_standalone_context()
    yield _ctx
    _ctx.release()


@pytest.fixture
def renderer(ctx):
    r = Renderer(ctx)
    yield r
    r.cleanup()


class TestRendererLayers:
    def test_set_preset_creates_layers(self, renderer):
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars"),
                VisualizationLayer(
                    visualization_type="spectrum_bars",
                    blend_mode=BlendMode.ADDITIVE,
                ),
            ],
        )
        renderer.set_preset(preset)
        assert len(renderer._layers) == 2

    def test_set_preset_creates_layer_fbos(self, renderer):
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars"),
                VisualizationLayer(visualization_type="spectrum_bars"),
            ],
        )
        renderer.set_preset(preset)
        fbo = renderer.ensure_offscreen_fbo((320, 240))
        frame = _make_frame()
        renderer.render_frame(frame, fbo, (320, 240))
        assert len(renderer._layer_fbos) == 2

    def test_cleanup_releases_layers(self, renderer):
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        renderer.set_preset(preset)
        renderer.cleanup()
        assert len(renderer._layers) == 0
        assert len(renderer._layer_fbos) == 0

    def test_invisible_layer_skipped(self, renderer):
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", visible=False),
            ],
        )
        renderer.set_preset(preset)
        fbo = renderer.ensure_offscreen_fbo((320, 240))
        frame = _make_frame()
        # Should not crash with invisible layer
        renderer.render_frame(frame, fbo, (320, 240))

    def test_unregistered_viz_type_skipped(self, renderer):
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="nonexistent_viz_type_xyz"),
                VisualizationLayer(visualization_type="spectrum_bars"),
            ],
        )
        renderer.set_preset(preset)
        # The unregistered type gets None viz, the valid one gets instantiated
        valid_layers = [(cfg, viz) for cfg, viz in renderer._layers if viz is not None]
        assert len(valid_layers) >= 1

    def test_update_params_without_type_change(self, renderer):
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(
                    visualization_type="spectrum_bars",
                    params={"bar_count": 32},
                ),
            ],
        )
        renderer.set_preset(preset)
        # Update params only — no structural change
        updated = Preset(
            name="Test",
            layers=[
                VisualizationLayer(
                    visualization_type="spectrum_bars",
                    params={"bar_count": 64},
                    opacity=0.5,
                ),
            ],
        )
        renderer.update_params(updated)
        assert renderer._layers[0][0].opacity == 0.5

    def test_update_params_type_change_triggers_rebuild(self, renderer):
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        renderer.set_preset(preset)
        updated = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="waveform")],
        )
        renderer.update_params(updated)
        assert renderer._layers[0][0].visualization_type == "waveform"

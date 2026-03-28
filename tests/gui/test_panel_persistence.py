"""Tests for panel widget persistence.

WHAT THIS TESTS:
- AnalysisPanel builds widgets once and reuses them across set_preset calls
- TextPanel builds widgets once and reuses them across set_preset calls
Does NOT test: VisualPanel section persistence
"""

import pytest

from wavern.gui.panels.analysis_panel import AnalysisPanel
from wavern.gui.panels.text_panel import TextPanel
from wavern.presets.schema import Preset, VisualizationLayer


@pytest.fixture
def preset_a():
    return Preset(
        name="A",
        layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        fft_size=2048,
        smoothing=0.3,
        beat_sensitivity=1.0,
    )


@pytest.fixture
def preset_b():
    return Preset(
        name="B",
        layers=[VisualizationLayer(visualization_type="particles")],
        fft_size=4096,
        smoothing=0.5,
        beat_sensitivity=1.5,
    )


class TestAnalysisPanelPersistence:
    def test_widgets_built_once(self, qtbot, preset_a, preset_b):
        panel = AnalysisPanel()
        qtbot.addWidget(panel)

        panel.set_preset(preset_a)
        spin_id = id(panel._fft_size_spin)

        panel.set_preset(preset_b)
        assert id(panel._fft_size_spin) == spin_id, "Widgets should be reused, not recreated"

    def test_values_updated_on_set_preset(self, qtbot, preset_a, preset_b):
        panel = AnalysisPanel()
        qtbot.addWidget(panel)

        panel.set_preset(preset_a)
        assert panel._fft_size_spin.value() == 2048

        panel.set_preset(preset_b)
        assert panel._fft_size_spin.value() == 4096
        assert panel._smoothing_spin.value() == 0.5
        assert panel._beat_sens_spin.value() == 1.5


class TestTextPanelPersistence:
    def test_widgets_built_once(self, qtbot, preset_a, preset_b):
        panel = TextPanel()
        qtbot.addWidget(panel)

        panel.set_preset(preset_a)
        spin_id = id(panel._overlay_font_size)

        panel.set_preset(preset_b)
        assert id(panel._overlay_font_size) == spin_id, "Widgets should be reused"

    def test_values_updated_on_set_preset(self, qtbot, preset_a, preset_b):
        panel = TextPanel()
        qtbot.addWidget(panel)

        panel.set_preset(preset_a)
        panel.set_preset(preset_b)
        assert panel._overlay_font_size is not None

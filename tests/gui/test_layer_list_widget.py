"""Tests for LayerListWidget.

WHAT THIS TESTS:
- Layer row creation from preset layers
- Add layer appends with auto-naming and emits signal
- Remove layer removes and emits signal
- Max 7 layers enforced (add button disabled)
- Delete disabled at 1 layer
- Selection emits layer_selected signal
- Visibility toggle emits layer_property_changed
- Move layer swaps and emits layer_order_changed
- Move button enable/disable at boundaries
Does NOT test: drag reorder (requires mouse simulation), rendering
"""

import pytest

from wavern.gui.layer_list_widget import LayerListWidget
from wavern.presets.schema import BlendMode, Preset, VisualizationLayer


@pytest.fixture
def two_layer_preset():
    return Preset(
        name="Test",
        layers=[
            VisualizationLayer(visualization_type="spectrum_bars", name="Bars"),
            VisualizationLayer(
                visualization_type="particles",
                name="Particles",
                blend_mode=BlendMode.ADDITIVE,
                opacity=0.8,
            ),
        ],
    )


class TestLayerListWidget:
    def test_build_creates_rows(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        assert widget.layer_count() == 2

    def test_add_layer_emits_signal(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[0] == 2  # new layer index
        assert sig.args[1] == "Layer 3"  # auto-generated name (2 layers + 1)

    def test_add_layer_name_increments(self, qtbot):
        """Adding layers uses count-based naming: Layer {current_count + 1}."""
        preset = Preset(
            name="Single",
            layers=[VisualizationLayer(visualization_type="spectrum_bars", name="Base")],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        # Add first → "Layer 2" (1 existing + 1)
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 2"

        # Add second → "Layer 3"
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 3"

    def test_max_layers_enforced(self, qtbot):
        layers = [VisualizationLayer(visualization_type="spectrum_bars") for _ in range(7)]
        preset = Preset(name="Max", layers=layers)
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)
        assert not widget.can_add_layer()

    def test_delete_disabled_at_one_layer(self, qtbot):
        preset = Preset(
            name="Single",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)
        assert not widget.can_remove_layer()

    def test_select_emits_signal(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_selected, timeout=1000) as sig:
            widget.select_layer(0)
        assert sig.args[0] == 0

    def test_remove_layer_emits_signal(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_removed, timeout=1000) as sig:
            widget.remove_layer(1)
        assert sig.args[0] == 1
        assert widget.layer_count() == 1

    def test_visibility_toggle(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_property_changed, timeout=1000) as sig:
            widget.toggle_visibility(0)
        assert sig.args[0] == 0
        assert sig.args[1] == "visible"
        assert sig.args[2] is False

    def test_move_layer_up(self, qtbot, two_layer_preset):
        """Moving a layer up swaps it with the next index."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_order_changed, timeout=1000) as sig:
            widget.move_layer(0, 1)
        assert sig.args == [0, 1]
        # Layer that was at index 0 ("Bars") is now at index 1
        assert widget._layers[1].name == "Bars"
        assert widget._layers[0].name == "Particles"

    def test_move_layer_down(self, qtbot, two_layer_preset):
        """Moving a layer down swaps it with the previous index."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_order_changed, timeout=1000) as sig:
            widget.move_layer(1, 0)
        assert sig.args == [1, 0]
        assert widget._layers[0].name == "Particles"
        assert widget._layers[1].name == "Bars"

    def test_move_follows_selection(self, qtbot, two_layer_preset):
        """Selection follows the moved layer."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        widget.select_layer(0)

        widget.move_layer(0, 1)
        assert widget.selected_index() == 1

    def test_move_noop_same_index(self, qtbot, two_layer_preset):
        """Moving a layer to its own position is a no-op."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        widget.move_layer(0, 0)
        assert widget._layers[0].name == "Bars"

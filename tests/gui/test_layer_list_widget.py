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
- Clone layer duplicates with correct name, params, and insertion position
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
        # Existing layers are "Bars"/"Particles" (not "Layer N"), so first gap is 1
        assert sig.args[1] == "Layer 1"

    def test_add_layer_selects_new_layer(self, qtbot, two_layer_preset):
        """Adding a layer should auto-select it."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        widget.select_layer(0)

        with qtbot.waitSignal(widget.layer_selected, timeout=1000):
            widget.add_layer()
        assert widget.selected_index() == 2  # the newly added layer

    def test_add_layer_name_increments(self, qtbot):
        """Adding layers fills gaps then increments: Layer 1, Layer 2, ..."""
        preset = Preset(
            name="Single",
            layers=[VisualizationLayer(visualization_type="spectrum_bars", name="Base")],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        # "Base" isn't "Layer N", so first gap is 1
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 1"

        # Next gap is 2
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 2"

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


class TestCloneLayer:
    def test_clone_layer_emits_signal(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        with qtbot.waitSignal(widget.layer_cloned, timeout=1000) as sig:
            widget.clone_layer(0)
        assert sig.args[0] == 1  # inserted right after index 0

    def test_clone_layer_name(self, qtbot, two_layer_preset):
        """Cloned layer is named cloned_<original_name>."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        widget.clone_layer(0)
        assert widget._layers[1].name == "cloned_Bars"

    def test_clone_preserves_params(self, qtbot):
        """Cloned layer keeps visualization_type, params, colors, blend, opacity."""
        original = VisualizationLayer(
            visualization_type="particles",
            name="Src",
            params={"count": 500, "speed": 1.5},
            colors=["#FF0000", "#00FF00"],
            blend_mode=BlendMode.SCREEN,
            opacity=0.6,
        )
        preset = Preset(name="Test", layers=[original])
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.clone_layer(0)
        clone = widget._layers[1]
        assert clone.visualization_type == "particles"
        assert clone.params == {"count": 500, "speed": 1.5}
        assert clone.colors == ["#FF0000", "#00FF00"]
        assert clone.blend_mode == BlendMode.SCREEN
        assert clone.opacity == 0.6
        assert clone.name == "cloned_Src"

    def test_clone_inserts_after_original(self, qtbot, two_layer_preset):
        """Clone is inserted at index+1, not appended to end."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        widget.clone_layer(0)
        assert widget.layer_count() == 3
        assert widget._layers[0].name == "Bars"
        assert widget._layers[1].name == "cloned_Bars"
        assert widget._layers[2].name == "Particles"

    def test_clone_selects_new_layer(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        widget.clone_layer(0)
        assert widget.selected_index() == 1

    def test_clone_name_falls_back_to_viz_type(self, qtbot):
        """When layer has no name, clone uses visualization_type."""
        layer = VisualizationLayer(visualization_type="particles", name="")
        preset = Preset(name="Test", layers=[layer])
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.clone_layer(0)
        assert widget._layers[1].name == "cloned_particles"

    def test_clone_params_independent(self, qtbot):
        """Mutating cloned layer params must not affect the original."""
        original = VisualizationLayer(
            visualization_type="spectrum_bars",
            name="Src",
            params={"bar_count": 64},
        )
        preset = Preset(name="Test", layers=[original])
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.clone_layer(0)
        clone = widget._layers[1]
        clone.params["bar_count"] = 128

        assert widget._layers[0].params["bar_count"] == 64

    def test_clone_object_identity_independent(self, qtbot):
        """Cloned layer in _layers must be a distinct object from the original."""
        original = VisualizationLayer(
            visualization_type="spectrum_bars",
            name="Src",
            params={"bar_count": 64},
            colors=["#FF0000"],
        )
        preset = Preset(name="Test", layers=[original])
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.clone_layer(0)

        # They must be different objects entirely
        assert widget._layers[0] is not widget._layers[1]
        # And nested mutable containers must also be independent
        assert widget._layers[0].params is not widget._layers[1].params
        assert widget._layers[0].colors is not widget._layers[1].colors

    def test_clone_blocked_at_max_layers(self, qtbot):
        """Cloning does nothing when already at 7 layers."""
        layers = [
            VisualizationLayer(visualization_type="spectrum_bars", name=f"L{i}")
            for i in range(7)
        ]
        preset = Preset(name="Max", layers=layers)
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.clone_layer(0)
        assert widget.layer_count() == 7  # unchanged


class TestLayerListApply:
    def test_apply_reuses_existing_rows(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        row_ids = [id(r) for r in widget._rows]

        widget.apply(two_layer_preset.layers)
        new_row_ids = [id(r) for r in widget._rows]
        assert row_ids == new_row_ids, "Existing rows should be reused"

    def test_apply_adds_rows_on_increase(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        three_layers = list(two_layer_preset.layers) + [
            VisualizationLayer(visualization_type="waveform", name="Wave")
        ]
        widget.apply(three_layers)
        assert widget.layer_count() == 3

    def test_apply_removes_rows_on_decrease(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        one_layer = [two_layer_preset.layers[0]]
        widget.apply(one_layer)
        assert widget.layer_count() == 1

    def test_apply_updates_values_in_place(self, qtbot, two_layer_preset):
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)

        modified = [
            two_layer_preset.layers[0].model_copy(update={"name": "Renamed"}),
            two_layer_preset.layers[1],
        ]
        widget.apply(modified)
        assert widget._rows[0]._name_edit.text() == "Renamed"


class TestLayerNaming:
    def test_add_after_delete_reuses_number(self, qtbot):
        """Deleting a layer then adding should reuse the freed number."""
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", name="Layer 1"),
                VisualizationLayer(visualization_type="spectrum_bars", name="Layer 2"),
            ],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        widget.remove_layer(1)  # remove "Layer 2"
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 2"  # should reuse, not "Layer 3"

    def test_add_after_apply_resets_counter(self, qtbot):
        """Calling apply() with new layers should not carry over stale counter."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        # Build with 5 layers, add 2 more to push counter high
        layers_5 = [
            VisualizationLayer(visualization_type="spectrum_bars", name=f"Layer {i + 1}")
            for i in range(5)
        ]
        widget.build(layers_5)
        widget.add_layer()  # "Layer 6"
        widget.add_layer()  # "Layer 7" -- counter is now at 8

        # Now apply a fresh 2-layer preset
        fresh = [
            VisualizationLayer(visualization_type="spectrum_bars", name="Layer 1"),
            VisualizationLayer(visualization_type="spectrum_bars", name="Layer 2"),
        ]
        widget.apply(fresh)

        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 3"  # not "Layer 8"

    def test_clone_then_add_skips_used_numbers(self, qtbot):
        """After cloning, new layer name should skip numbers in use."""
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", name="Layer 1"),
                VisualizationLayer(visualization_type="spectrum_bars", name="Layer 2"),
            ],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)

        # Clone doesn't use "Layer N" naming, so next add should be "Layer 3"
        widget.clone_layer(0)
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        assert sig.args[1] == "Layer 3"

    def test_naming_max_is_bounded(self, qtbot):
        """Layer name numbers should never exceed reasonable bounds."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        # Simulate repeated add/delete cycles
        for _ in range(10):
            widget.build(
                [VisualizationLayer(visualization_type="spectrum_bars", name="Layer 1")]
            )
            for _ in range(6):
                widget.add_layer()
            for i in range(6, 0, -1):
                widget.remove_layer(i)

        # After all that churn, next add should still be reasonable
        with qtbot.waitSignal(widget.layer_added, timeout=1000) as sig:
            widget.add_layer()
        name = sig.args[1]
        num = int(name.split()[-1])
        assert num <= 7, f"Layer number {num} exceeds max layer count"


class TestDeleteSelection:
    def test_delete_selected_selects_neighbor(self, qtbot, two_layer_preset):
        """Deleting the selected layer should auto-select a neighbor."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        widget.select_layer(1)  # select "Particles"

        widget.remove_layer(1)
        assert widget.selected_index() != -1, "Should auto-select, not leave -1"
        assert widget.selected_index() == 0  # only remaining layer

    def test_delete_first_of_three_selects_next(self, qtbot):
        """Deleting layer 0 of 3 should select the new layer 0."""
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", name="A"),
                VisualizationLayer(visualization_type="spectrum_bars", name="B"),
                VisualizationLayer(visualization_type="spectrum_bars", name="C"),
            ],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)
        widget.select_layer(0)

        widget.remove_layer(0)
        assert widget.selected_index() == 0
        assert widget._layers[0].name == "B"

    def test_delete_middle_selects_same_index(self, qtbot):
        """Deleting middle layer should select the layer that slides into its position."""
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", name="A"),
                VisualizationLayer(visualization_type="spectrum_bars", name="B"),
                VisualizationLayer(visualization_type="spectrum_bars", name="C"),
            ],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)
        widget.select_layer(1)  # select "B"

        widget.remove_layer(1)  # delete "B"
        assert widget.selected_index() == 1  # now pointing at "C"
        assert widget._layers[1].name == "C"

    def test_delete_last_selects_new_last(self, qtbot):
        """Deleting the last layer should select the new last layer."""
        preset = Preset(
            name="Test",
            layers=[
                VisualizationLayer(visualization_type="spectrum_bars", name="A"),
                VisualizationLayer(visualization_type="spectrum_bars", name="B"),
                VisualizationLayer(visualization_type="spectrum_bars", name="C"),
            ],
        )
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(preset.layers)
        widget.select_layer(2)  # select "C" (last)

        widget.remove_layer(2)
        assert widget.selected_index() == 1  # new last layer "B"

    def test_delete_emits_layer_selected(self, qtbot, two_layer_preset):
        """Deleting selected layer should emit layer_selected for the new selection."""
        widget = LayerListWidget()
        qtbot.addWidget(widget)
        widget.build(two_layer_preset.layers)
        widget.select_layer(1)

        with qtbot.waitSignal(widget.layer_selected, timeout=1000) as sig:
            widget.remove_layer(1)
        assert sig.args[0] == 0  # auto-selected the remaining layer

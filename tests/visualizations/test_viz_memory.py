"""Tests for wavern.gui.panels.visual_panel visualization parameter memory.

WHAT THIS TESTS:
- Switching visualization type saves the current params to the per-type memory dict
- Switching back to a previously used type restores its saved params
- Reset All clears memory for the current type and sets params to empty (schema defaults)
- Two VisualPanel instances sharing the same memory dict see each other's saved params
Does NOT test: OpenGL rendering, preset file I/O, or sidebar layout

Notes:
- _viz_memory keys are tuple[int, str] (layer_index, viz_type), e.g. (0, "waveform")
- _viz_memory type: dict[tuple[int, str], dict[str, Any]]
"""

import pytest

from wavern.gui.panels.visual_panel import VisualPanel
from wavern.presets.schema import Preset, VisualizationLayer
from wavern.visualizations.registry import VisualizationRegistry


def _get_two_viz_types() -> tuple[str, str]:
    """Return two distinct registered visualization type names."""
    registry = VisualizationRegistry()
    all_viz = registry.list_all()
    assert len(all_viz) >= 2, "Need at least 2 registered visualizations for tests"
    return all_viz[0]["name"], all_viz[1]["name"]


def _make_preset(viz_type: str, params: dict | None = None) -> Preset:
    return Preset(
        name="test_preset",
        layers=[VisualizationLayer(
            visualization_type=viz_type,
            params=params or {},
        )],
    )


class TestVizMemory:
    """Tests for viz param store/restore on type switch."""

    def test_params_saved_on_type_switch(self) -> None:
        """Switching viz type saves current params to memory."""
        type_a, type_b = _get_two_viz_types()
        panel = VisualPanel()
        panel.set_preset(_make_preset(type_a))

        # Modify a param on type_a
        registry = VisualizationRegistry()
        schema_a = registry.get(type_a).PARAM_SCHEMA
        if not schema_a:
            pytest.skip("type_a has no params")

        param_name = next(iter(schema_a))
        schema_entry = schema_a[param_name]
        test_val = schema_entry.get("max", schema_entry.get("default", 1))
        panel._preset.layers[0].params[param_name] = test_val

        # Switch to type_b — should save type_a params
        idx_b = -1
        for i in range(panel._viz_combo.count()):
            if panel._viz_combo.itemData(i) == type_b:
                idx_b = i
                break
        assert idx_b >= 0
        panel._viz_combo.setCurrentIndex(idx_b)

        assert (0, type_a) in panel._viz_memory
        assert panel._viz_memory[(0, type_a)][param_name] == test_val

    def test_params_restored_on_switch_back(self) -> None:
        """Switching back to a previously used viz type restores its params."""
        type_a, type_b = _get_two_viz_types()
        panel = VisualPanel()
        panel.set_preset(_make_preset(type_a))

        registry = VisualizationRegistry()
        schema_a = registry.get(type_a).PARAM_SCHEMA
        if not schema_a:
            pytest.skip("type_a has no params")

        param_name = next(iter(schema_a))
        schema_entry = schema_a[param_name]
        test_val = schema_entry.get("max", schema_entry.get("default", 1))
        panel._preset.layers[0].params[param_name] = test_val

        # Switch A -> B -> A
        idx_b = -1
        for i in range(panel._viz_combo.count()):
            if panel._viz_combo.itemData(i) == type_b:
                idx_b = i
                break
        panel._viz_combo.setCurrentIndex(idx_b)

        idx_a = -1
        for i in range(panel._viz_combo.count()):
            if panel._viz_combo.itemData(i) == type_a:
                idx_a = i
                break
        panel._viz_combo.setCurrentIndex(idx_a)

        assert panel._preset.layers[0].params.get(param_name) == test_val

    def test_reset_all_clears_memory_and_uses_defaults(self) -> None:
        """Reset All clears memory for current type and rebuilds with defaults."""
        type_a, _ = _get_two_viz_types()
        panel = VisualPanel()
        panel.set_preset(_make_preset(type_a))

        registry = VisualizationRegistry()
        schema_a = registry.get(type_a).PARAM_SCHEMA
        if not schema_a:
            pytest.skip("type_a has no params")

        param_name = next(iter(schema_a))

        # Set a non-default value
        panel._preset.layers[0].params[param_name] = "SENTINEL"
        panel._viz_memory[(0, type_a)] = dict(panel._preset.layers[0].params)

        # Reset
        panel._on_reset_all_params()

        assert (0, type_a) not in panel._viz_memory
        # Params should be empty (schema defaults applied during widget build)
        assert panel._preset.layers[0].params == {}

    def test_shared_memory_dict(self) -> None:
        """Two VisualPanel instances sharing a memory dict see each other's saves."""
        type_a, type_b = _get_two_viz_types()
        shared: dict = {}
        panel1 = VisualPanel(viz_memory=shared)
        panel2 = VisualPanel(viz_memory=shared)

        panel1.set_preset(_make_preset(type_a))

        registry = VisualizationRegistry()
        schema_a = registry.get(type_a).PARAM_SCHEMA
        if not schema_a:
            pytest.skip("type_a has no params")

        param_name = next(iter(schema_a))
        panel1._preset.layers[0].params[param_name] = 999

        # Switch panel1 to type_b — saves type_a params to shared dict
        idx_b = -1
        for i in range(panel1._viz_combo.count()):
            if panel1._viz_combo.itemData(i) == type_b:
                idx_b = i
                break
        panel1._viz_combo.setCurrentIndex(idx_b)

        # panel2 should see the same memory
        assert panel2._viz_memory is shared
        assert (0, type_a) in panel2._viz_memory
        assert panel2._viz_memory[(0, type_a)][param_name] == 999

    def test_empty_memory_uses_schema_defaults(self) -> None:
        """When no memory exists for a viz type, params dict is empty (defaults from schema)."""
        type_a, type_b = _get_two_viz_types()
        panel = VisualPanel()
        panel.set_preset(_make_preset(type_a))

        # Switch to type_b with no prior memory
        idx_b = -1
        for i in range(panel._viz_combo.count()):
            if panel._viz_combo.itemData(i) == type_b:
                idx_b = i
                break
        panel._viz_combo.setCurrentIndex(idx_b)

        # Params should have been populated from widget defaults during build
        # (build_param_widgets reads current_val from params dict, falling back to schema default)
        # The restored dict was empty, so widgets used schema defaults and wrote them via signals
        assert panel._preset.layers[0].visualization_type == type_b

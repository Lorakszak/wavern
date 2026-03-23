"""Common validation tests for ALL registered visualizations.

WHAT THIS TESTS:
- Every registered visualization has NAME, DISPLAY_NAME, CATEGORY, DESCRIPTION
- Every PARAM_SCHEMA entry has a 'type' and 'default' field
- All int/float params have min <= default <= max
- All choice params have a 'choices' list containing the default
- All bool params have a bool default
Does NOT test: OpenGL rendering, GPU initialization, preset JSON files (see test_all_presets),
or visualization-specific logic (see per-viz test files)
"""

from __future__ import annotations

import pytest

from wavern.visualizations.registry import VisualizationRegistry

# Ensure all built-in visualizations are registered
import wavern.visualizations  # noqa: F401

_registry = VisualizationRegistry()
_ALL_VIZ_NAMES = _registry.list_names()


@pytest.fixture(params=_ALL_VIZ_NAMES)
def viz_class(request: pytest.FixtureRequest) -> type:
    """Yield each registered visualization class."""
    return _registry.get(request.param)


class TestRegistration:
    """Every visualization has the required class attributes."""

    def test_has_name(self, viz_class: type) -> None:
        assert isinstance(viz_class.NAME, str)
        assert len(viz_class.NAME) > 0

    def test_has_display_name(self, viz_class: type) -> None:
        assert isinstance(viz_class.DISPLAY_NAME, str)
        assert len(viz_class.DISPLAY_NAME) > 0

    def test_has_category(self, viz_class: type) -> None:
        assert isinstance(viz_class.CATEGORY, str)

    def test_has_description(self, viz_class: type) -> None:
        assert isinstance(viz_class.DESCRIPTION, str)

    def test_has_param_schema(self, viz_class: type) -> None:
        assert isinstance(viz_class.PARAM_SCHEMA, dict)


class TestParamSchemaStructure:
    """Every PARAM_SCHEMA entry is well-formed."""

    def test_all_entries_have_type_and_default(self, viz_class: type) -> None:
        for key, entry in viz_class.PARAM_SCHEMA.items():
            assert "type" in entry, f"{viz_class.NAME}.{key}: missing 'type'"
            assert "default" in entry, f"{viz_class.NAME}.{key}: missing 'default'"

    def test_int_float_defaults_in_range(self, viz_class: type) -> None:
        for key, entry in viz_class.PARAM_SCHEMA.items():
            if entry["type"] not in ("int", "float"):
                continue
            assert "min" in entry, f"{viz_class.NAME}.{key}: missing 'min'"
            assert "max" in entry, f"{viz_class.NAME}.{key}: missing 'max'"
            assert entry["min"] <= entry["default"] <= entry["max"], (
                f"{viz_class.NAME}.{key}: default {entry['default']} "
                f"not in [{entry['min']}, {entry['max']}]"
            )

    def test_choice_defaults_valid(self, viz_class: type) -> None:
        for key, entry in viz_class.PARAM_SCHEMA.items():
            if entry["type"] != "choice":
                continue
            assert "choices" in entry, f"{viz_class.NAME}.{key}: missing 'choices'"
            assert entry["default"] in entry["choices"], (
                f"{viz_class.NAME}.{key}: default {entry['default']!r} "
                f"not in {entry['choices']}"
            )

    def test_bool_defaults_are_bool(self, viz_class: type) -> None:
        for key, entry in viz_class.PARAM_SCHEMA.items():
            if entry["type"] != "bool":
                continue
            assert isinstance(entry["default"], bool), (
                f"{viz_class.NAME}.{key}: default {entry['default']!r} is not bool"
            )

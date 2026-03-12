"""Tests for VisualizationRegistry."""

import pytest

from wavern.visualizations.registry import VisualizationRegistry


class TestVisualizationRegistry:
    def test_builtin_visualizations_registered(self):
        import wavern.visualizations  # noqa: F401

        registry = VisualizationRegistry()
        names = registry.list_names()

        assert "spectrum_bars" in names
        assert "waveform" in names
        assert "circular_spectrum" in names
        assert "particles" in names
        assert "smoky_waves" in names

    def test_get_existing(self):
        import wavern.visualizations  # noqa: F401

        registry = VisualizationRegistry()
        cls = registry.get("spectrum_bars")
        assert cls.NAME == "spectrum_bars"
        assert cls.DISPLAY_NAME == "Spectrum Bars"

    def test_get_nonexistent(self):
        registry = VisualizationRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent_viz")

    def test_list_all(self):
        import wavern.visualizations  # noqa: F401

        registry = VisualizationRegistry()
        all_viz = registry.list_all()

        assert len(all_viz) >= 5
        for info in all_viz:
            assert "name" in info
            assert "display_name" in info
            assert "category" in info
            assert "description" in info

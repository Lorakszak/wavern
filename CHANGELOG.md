# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1-alpha.1] — 2026-03-12

### Added

- Initial implementation: 5 built-in visualizations (Spectrum Bars, Classic Waveform, Circular
  Spectrum, Particle Burst, Smoky Waves)
- Preset system: pydantic schema, built-in JSON presets, user preset directory
  (`~/.config/wavern/presets/`)
- Headless CLI export via `uv run wavern render` (H.264/MP4 and VP9/WebM with alpha)
- PySide6 GUI with real-time OpenGL 3.3+ preview, settings panel, and color palette editor
- Plugin system: drop a `.py` file in `~/.config/wavern/plugins/` to register custom
  visualizations
- `@register` decorator and `AbstractVisualization` ABC for the visualization plugin API
- `FrameAnalysis` dataclass as the universal audio contract between analyzer and visualizations
- Shared `Renderer` used identically for GUI preview and headless export
- 27-test pytest suite covering core, visualizations, presets, and CLI

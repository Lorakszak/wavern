# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- 3 new visualizations: Lissajous (Alpha), Radial Waveform (Alpha), Spectrogram (Alpha)
  - Lissajous: phase-portrait (X=waveform[i], Y=waveform[i+delay]), rotational symmetry 1–8, beat-reactive glow
  - Radial Waveform: time-domain waveform wrapped around a circle with optional center image, mirror modes, beat-reactive pulse
  - Spectrogram: scrolling frequency heatmap, 4 scroll directions, 6 colormaps (inferno/magma/viridis/plasma/grayscale/palette), log/mel/linear scale, Gaussian blur
- 21 new showcase presets (28 total built-in): aurora_borealis, bouncing_orbit, cyberpunk_skyline, deep_ocean_pulse, ghost_signal, kaleidoscope, lissajous, mirror_cathedral, neon_flood, neon_fortress, oscilloscope, pulsing_cage, radial_waveform, rect_spectrum, reverse_vortex, shadow_cascade, shadow_halo, shadow_monolith, solar_corona, stardust_rain, vertical_rainfall, volcanic_eruption (7 marked Beta)
- Video background support via PyAV: seeking, caching, looping
- Background movement effects: drift, shake, wave, zoom_pulse, breathe — with speed, intensity, angle, and clamp_to_frame controls
- Background transforms for all background types: rotation (0–360°), mirror X/Y
- Video overlay compositing above visualization: alpha, additive, screen blend modes; opacity and transform controls
- Preset favorites system with persistence to `~/.config/wavern/favorites.json`; context-menu and dedicated button in preset panel
- Preset source filter (All / Built-in / User) and item size toggle (S/M/L) in preset panel, both persisted
- Dual tabbed sidebars with vertical split mode; cross-sidebar sync via `_rebuilding` guard
- 5 QSS themes: dark, light, nord, dracula, gruvbox — menu-based switching with session persistence
- `DragSpinBox`: drag-to-change, click-to-edit, per-widget reset button (↺), scroll-ignore
- `NoScrollComboBox`: ignores accidental scroll-wheel input on combos
- Decomposed settings panels: VisualPanel, TextPanel, AnalysisPanel, ExportPanel (replaced monolithic settings_panel.py)
- dB magnitude system: running-peak normalization, per-band auto-gain, asymmetric envelope followers (10 ms attack / 200 ms release)
- Bass-weighted beat detection with adaptive threshold and graduated beat intensity
- Amplitude envelope for glow and framerate-independent image bounce
- Bar spacing parameter (replaces `bar_width_ratio`) for spectrum_bars, circular_spectrum, rect_spectrum
- Min bar height parameter for spectrum_bars and circular_spectrum (keeps bars visible in silent passages)
- Universal `height_reference` mode for spectrum_bars: per_bar or absolute y-position color mapping
- Continuous color gradient for rect_spectrum (mirrors gradient direction on left/right sides)
- Output filename field in export settings panel
- Export panel Reset All button
- First-frame render: update preview without playback
- "Disable Preview" checkbox for background/overlay (skips GUI preview, renders in export)
- "Open Directory" button in export completion dialog
- 18 test files, ~500+ test cases (up from 27)

### Fixed

- C++ use-after-delete crash on background widget rebuild (clear stale attrs before rebuild)
- Spectral flux was always 0 (broken onset detection)
- Bar gaps invisible at high bar counts (unit mismatch in spacing calculation)
- High bar count crash: raised `u_magnitudes` uniform array from 128 to 256 entries
- Rect spectrum `mirror_sides` color bug: colors now follow physical position, not mirrored magnitude index
- Smoky waves vertical centering incorrect at higher wave counts
- Odd `bar_count` crash: moved mirror_spectrum logic to shaders
- Preset panel buttons rendered off-screen (scrolling architecture rework)
- Sidebar default width too narrow (increased to 430 px)
- Video overlay loop lag: flush decoder buffers on seek

### Changed

- `Ctrl+S` remapped to Save Preset As (was `Ctrl+Shift+S`); old auto-numbered save removed
- Visualization stability markers: Beta — Classic Waveform, Particle Burst, Smoky Waves; Alpha — Lissajous, Radial Waveform, Spectrogram
- Visualization shortcuts (Ctrl+1…N) now match `list_all()` insertion order dynamically
- ~500 ms drag lag eliminated via incremental `update_values()` in panels (full rebuild only on structural changes)

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

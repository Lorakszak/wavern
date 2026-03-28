# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0-alpha.1] - 2026-03-28

### Added

#### Visualizations

- 5 new visualizations (10 total):
  - CRT Oscilloscope: retro phosphor glow, scanlines, screen curvature, beat-reactive bloom
  - Tunnel: infinite tunnel effect with depth-based coloring and beat-reactive speed
  - Lissajous (Alpha): phase-portrait (X=waveform[i], Y=waveform[i+delay]), rotational symmetry 1-8, beat-reactive glow
  - Radial Waveform (Alpha): time-domain waveform wrapped around a circle with optional center image, mirror modes, beat-reactive pulse
  - Spectrogram (Alpha): scrolling frequency heatmap, 4 scroll directions, 6 colormaps (inferno/magma/viridis/plasma/grayscale/palette), log/mel/linear scale, Gaussian blur
- Overhauled particles visualization: spawn modes, forces, audio reactivity, lifecycle management, off-screen spawn origins
- 31 new showcase presets (36 total built-in): aurora_borealis, bouncing_orbit, closing_walls, cyberpunk_skyline, deep_ocean_pulse, fireflies, ghost_signal, kaleidoscope, lissajous, mirror_cathedral, monsoon, neon_flood, neon_fortress, oscilloscope, oscilloscope_busted_crt, oscilloscope_green_phosphor, oscilloscope_neon, pulsing_cage, radial_waveform, rect_spectrum, reverse_vortex, shadow_cascade, shadow_halo, shadow_monolith, solar_corona, spiral_galaxy, supernova, tunnel_emergence, tunnel_vortex, tunnel_warp, vertical_rainfall
- Visualization type filter dropdown in preset panel

#### Multi-Layer Compositing

- Multi-layer visualization support (1-7 layers per preset)
- Per-layer blend modes: Normal, Additive, Screen, Multiply
- Per-layer opacity control
- GLSL compositing shader (`composite.frag`) for layer blending
- Auto-migration of old single-viz presets via `_migrate_preset_data()`
- Default preset updated to showcase multi-layer compositing

#### Background and Global Effects

- 7 background effects: blur, hue_shift, saturation, brightness, pixelate, posterize, invert (applied via `bg_effects.frag`)
- 7 global post-processing effects: vignette, chromatic_aberration, glitch, film_grain, bloom, scanlines, color_shift (applied via `global_effects.frag`)
- Audio-reactive effect parameters
- Configurable apply stage (before/after overlays)
- Multiple simultaneous background movement effects
- Background effects work on all background types (solid, none, gradient, image, video)
- Video background support via PyAV: seeking, caching, looping
- Background movement effects: drift, shake, wave, zoom_pulse, breathe with speed, intensity, angle, and clamp_to_frame controls
- Background transforms for all background types: rotation (0-360 degrees), mirror X/Y
- Video overlay compositing above visualization: alpha, additive, screen blend modes; opacity and transform controls

#### Export

- Intro/outro video concatenation support
- Fade-in/fade-out support for rendered video
- Fade-in/fade-out support for intro/outro clips
- Render duration shown in completion popup
- Output filename field in export settings panel
- Export panel Reset All button
- "Open Directory" button in export completion dialog

#### GUI

- Loop button across all 5 themes with active state styling
- Ctrl+Shift+Tab to cycle visualizations in reverse
- Ctrl+0 shortcut for 10th visualization
- Visual tab sections start collapsed by default
- Dual tabbed sidebars with vertical split mode; cross-sidebar sync via `_rebuilding` guard
- 5 QSS themes: dark, light, nord, dracula, gruvbox with menu-based switching and session persistence
- `DragSpinBox`: drag-to-change, click-to-edit, per-widget reset button, scroll-ignore
- `NoScrollComboBox`: ignores accidental scroll-wheel input on combos
- Decomposed settings panels: VisualPanel, TextPanel, AnalysisPanel, ExportPanel (replaced monolithic settings_panel.py)
- Preset favorites system with persistence to `~/.config/wavern/favorites.json`; context-menu and dedicated button in preset panel
- Preset source filter (All / Built-in / User) and item size toggle (S/M/L) in preset panel, both persisted
- First-frame render: update preview without playback
- "Disable Preview" checkbox for background/overlay (skips GUI preview, renders in export)

#### Audio Analysis

- dB magnitude system: running-peak normalization, per-band auto-gain, asymmetric envelope followers (10 ms attack / 200 ms release)
- Bass-weighted beat detection with adaptive threshold and graduated beat intensity
- Amplitude envelope for glow and framerate-independent image bounce

#### Infrastructure

- Centralized logging system: rotating file log at `~/.config/wavern/wavern.log`, `--log-level` and `--log-file` CLI flags, `-v`/`--verbose` flag to stream logs to terminal, startup diagnostics banner, comprehensive debug logging across core/GUI/visualization modules
- Replaced mypy with pyright (standard mode) for static type checking
- Consolidated boilerplate visualization and preset tests
- Version sourced from `importlib.metadata` as single source of truth
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
- Export: close stdin and reap ffmpeg process on cancel
- Export: drain stderr concurrently to prevent pipe deadlock
- Export: replace `_cancelled` bool with `threading.Event`
- Export: add timeout to `subprocess.run` in mux and GIF passes
- GUI: stop export worker on dialog close to prevent crash
- GUI: initialize section widgets to None in `VisualPanel.__init__`
- GUI: replace hardcoded `parents[4]` with `Path.home()`
- GUI: only emit `seek_requested` on slider release
- GUI: wait for worker thread before accepting export dialog
- GUI: use public signals instead of private `_on_play_clicked`
- Viz: reallocate particle array when `max_particles` changes
- Viz: use `hex_to_rgb()` for safe shadow color parsing
- Viz: set texture to None between release and re-creation
- Viz: replace assert with early return in oscilloscope render
- Viz: use consistent `choice`/`choices` in PARAM_SCHEMA
- Renderer: release FBO before texture in `ensure_offscreen_fbo`
- Renderer: store VBOs on self and release in cleanup
- Renderer: always enable blending before visualization render
- Fonts: write downloaded font to temp file then rename atomically
- HWAccel: probe VAAPI render node at runtime instead of hardcoding
- Video: wrap `probe_fps` in try/except to return 0.0 as documented
- Video: use persistent decode generator to fix B-frame loop stutter
- Audio: acquire lock when setting `_playing` in pause/stop/play
- Audio: correct off-by-one in `seek()` clamp
- Presets: log errors instead of silently swallowing in manager
- Plugins: use `spec_from_file_location` instead of mutating `sys.path`
- Shaders: guard against division by zero in 7 fragment shaders
- Resolved all pyright and ruff errors across codebase

### Removed

- Presets: stardust_rain, volcanic_eruption, particle_burst

### Changed

- `Ctrl+S` remapped to Save Preset As (was `Ctrl+Shift+S`); old auto-numbered save removed
- Visualization stability markers: Particle Burst graduated to stable; CRT Oscilloscope and Tunnel added to README
- Visualization shortcuts (Ctrl+1...N) now match `list_all()` insertion order dynamically
- ~500 ms drag lag eliminated via incremental `update_values()` in panels (full rebuild only on structural changes)
- Scoped change routing and persistent panels for GUI performance
- Replaced deprecated `stateChanged` with `toggled` in GUI

### Performance

- Cache QSS stylesheets and skip redundant theme re-applies
- Binary search in `_check_beat` instead of linear scan

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

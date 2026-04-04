# Wavern — Project Instructions for AI Agents

## Quick Reference

- **Language**: Python 3.12 (strict: `>=3.12,<3.13`)
- **Package manager**: `uv` (not pip)
- **Build**: hatchling, src layout (`src/wavern/`)
- **Run GUI**: `uv run wavern gui`

## Setup

Install runtime dependencies:
```
uv sync
```

Install dev dependencies (pytest, pytest-qt, ruff, pyright) — required before running tests or checks:
```
uv sync --extra dev
```

## Quality Tools

Three tools gate every change. Run all three before considering work done:

| Tool | Command | Purpose |
|------|---------|---------|
| **ruff** | `uv run ruff check src/ tests/` | Linting (line-length 100, Python 3.12 target) |
| **pyright** | `uv run pyright src/` | Static type checking (standard mode) |
| **pytest** | `uv run pytest tests/ -v` | All tests must pass |

- **ruff**: Auto-fix safe issues with `uv run ruff check --fix src/ tests/`. Format with `uv run ruff format src/ tests/`.
- **pyright**: Runs in `standard` mode (configured in `pyproject.toml`). All new code must have type annotations that satisfy pyright.
- **pytest**: All tests must pass. See [Testing Policy](#testing-policy) for coverage expectations.

## Logging

Centralized in `src/wavern/logging_setup.py`, called from CLI entry points (`cli.py`). Two handlers:

- **Console** (`stderr`): defaults to WARNING for `gui`, INFO for `render`. Use `-v`/`--verbose` to stream all logs to terminal, or `--log-level` for fine-grained control.
- **File** (`~/.config/wavern/wavern.log`): always DEBUG, rotating 5 MB × 4 files (3 backups + 1 active). User-configurable via `--log-file`.

All modules use `logger = logging.getLogger(__name__)`. The `wavern` package logger is configured (not the root logger), so third-party noise is excluded. New modules must follow this pattern — never use `logging.basicConfig()` or `print()` for diagnostics.

## Architecture

### Source Layout

```
src/wavern/
  config.py       — centralised XDG config paths (get_config_directory, get_preset_directory, get_favorites_path)
  core/           — display-agnostic processing (no Qt imports)
    audio_loader.py, audio_analyzer.py, audio_player.py
    renderer.py, timeline.py, video_source.py
    text_overlay.py, font_manager.py
    export_config.py   — ExportConfig dataclass (shared between export and ffmpeg_cmd)
    export.py          — ExportPipeline (headless render loop + ffmpeg mux)
    ffmpeg_cmd.py      — build_ffmpeg_cmd() pure function
    gif_export.py      — two-pass GIF pipeline
    codecs.py, hwaccel.py
  visualizations/ — base ABC + image_mixin + 11 built-in types + registry
  presets/        — pydantic schema + manager + defaults/*.json
  shaders/        — GLSL 3.3 core (.vert/.frag), including composite.vert/.frag for layer blending
  gui/            — PySide6 widgets
    main_window.py     — top-level orchestrator
    gl_widget.py, sidebar.py, transport_bar.py, preset_panel.py
    menu_builder.py    — build_menu_bar() free function → dict[str, QAction]
    keyboard_handler.py — KeyboardHandler(QObject) app-level event filter
    export_dialog.py, export_worker.py
    favorites_store.py, theme_manager.py
    constants.py       — shared UI constants (quality presets, codec lists, resolutions)
    project_settings_panel.py — coordinator for ResolutionSection + QualitySection
    layer_list_widget.py   — multi-layer management (visibility, reorder, blend, opacity)
    background_picker.py, collapsible_section.py, drag_spinbox.py
    no_scroll_combo.py, help_button.py, file_import_dialog.py
  gui/panels/     — decomposed settings panels
    visual_panel.py    — coordinator: viz type + colors + background + overlay
    param_section.py, color_section.py, background_section.py, overlay_section.py
    resolution_section.py, quality_section.py
    text_panel.py, analysis_panel.py, export_panel.py
  gui/themes/     — QSS theme files (dark, light, nord, dracula, gruvbox)
  utils/          — color, math_utils
  logging_setup.py — centralized logging config (setup_logging, log_startup_banner)
  cli.py          — click CLI entry point
  app.py          — QApplication bootstrap
```

### Key Design Decisions

- **Renderer is display-agnostic**: `Renderer.render_frame(frame, fbo, resolution)` works identically for GUI preview (QOpenGLWidget) and headless export (standalone context). Never add GUI awareness to the renderer.
- **Visualization lifecycle**: `__init__(ctx, params)` → `initialize()` → `render()` per frame → `cleanup()`. GPU resources are created in `initialize()`, not `__init__`.
- **FrameAnalysis dataclass** is the universal audio contract. All visualizations receive it — never pass raw audio to render methods.
- **Preset** is a pydantic model. Built-in presets ship as JSON in `presets/defaults/`, user presets live at `~/.config/wavern/presets/`.
- **Multi-layer compositing**: `Preset.layers` is a list of `VisualizationLayer` (1–7). Each layer has its own `visualization_type`, `params`, `colors`, `blend_mode`, and `opacity`. The renderer renders each layer to its own FBO, then a GLSL compositing shader (`composite.frag`) blends them with per-layer blend mode (Normal/Additive/Screen/Multiply) and opacity. Old single-viz presets are auto-migrated on load via `_migrate_preset_data()`.
- **Config paths** are centralised in `config.py` — use `get_preset_directory()` and `get_favorites_path()` rather than inlining XDG logic.
- **Background effects work on all background types**: solid, none, gradient, image, and video. For solid/none (no texture), the renderer uses `_apply_bg_effects_standalone()` which copies the cleared FBO to an intermediate and runs the effects shader on it.
- **Background effects** (7): blur, hue_shift, saturation, brightness, pixelate, posterize, invert. Applied via `bg_effects.frag` in a fixed order: pixelate → blur → hue_shift → saturation → brightness → posterize → invert.
- **Global effects** (7): vignette, chromatic_aberration, glitch, film_grain, bloom, scanlines, color_shift. Applied via `global_effects.frag` in a fixed order: glitch → chromatic → bloom → color_shift → scanlines → grain → vignette. Can be applied before or after overlays via `apply_stage`.

### Critical Patterns

**Safe uniform setting**: GLSL compilers strip unused uniforms. Always use `self._set_uniform(prog, name, value)` and `self._write_uniform(prog, name, data)` from `AbstractVisualization` — never raw `prog[name].value = ...` which throws `KeyError` if optimized out.

**Uniform arrays**: moderngl doesn't support bracket-indexed uniform access (`prog["u_arr[0]"]`). Upload entire arrays via `prog["u_arr"].write(numpy_buffer.tobytes())`.

**Large uniform arrays**: Arrays over ~256 floats can exceed GPU constant register limits. Use textures instead (see `waveform.py` which uses a 2D texture of shape `(N, 1)` for waveform data).

**Signal blocking in Qt**: When rebuilding panel widgets programmatically, block signals on combo boxes (`blockSignals(True)`) before populating/setting values to prevent cascading `params_changed` emissions that wipe preset params. The `_rebuilding` flag on each panel guards against signal loops when syncing across dual sidebars.

**Section widget pattern**: Complex panels are decomposed into `QWidget` section subclasses. Each section owns its UI, emits focused signals, and exposes `collect() -> dict` for the coordinator to read. See `gui/panels/CLAUDE.md`.

**Renderer type change detection**: `renderer.update_params()` auto-detects when `visualization_type` changed and calls `set_preset()` internally. Callers don't need to distinguish param updates from type switches.

**Theme-styled buttons**: Small control buttons (▲/▼/x for reordering and removing) use `setObjectName("ColorControlBtn")`. The layer visibility toggle uses `setObjectName("LayerEyeBtn")` with `setCheckable(True)` — the theme controls checked/unchecked colors via QSS `:checked` pseudo-state. Never hardcode button colors; all 5 themes define these object-name styles.

**Transparent export**: Background type "none" exports with alpha via VP9/WebM (`yuva420p`). H.264/MP4 does not support alpha. VP9 requires `-b:v 0` for CRF mode + `-speed 4 -row-mt 1` for reasonable encode time.

## Adding a New Visualization

1. Create `src/wavern/visualizations/my_viz.py`
2. Subclass `AbstractVisualization`, set `NAME`, `DISPLAY_NAME`, `DESCRIPTION`, `CATEGORY`, `PARAM_SCHEMA`
3. Implement `initialize()`, `render()`, `cleanup()` — use `_set_uniform`/`_write_uniform` for all uniforms
4. Apply `@register` decorator
5. Add import to `src/wavern/visualizations/__init__.py`
6. Create matching preset JSON in `src/wavern/presets/defaults/`
7. Add tests covering registration, PARAM_SCHEMA structure, and preset JSON validity (see existing tests for examples)

## Testing Policy

Every PR must include tests for any new functionality introduced:

- **New visualizations**: test registration via `get_visualization(NAME)`, PARAM_SCHEMA field types, and that the preset JSON loads against the Preset schema.
- **New core features**: test the public interface of the changed module. Use real objects — do not mock internal subsystems (renderer, audio analyzer, preset manager).
- **Bug fixes**: add a regression test that would have caught the bug.
- **Refactors**: all existing tests must continue to pass; add tests for any newly exposed interfaces.

Run tests with: `uv run pytest tests/ -v`

### Test Directory Structure

Tests mirror the source layout:
```
tests/
  conftest.py, test_cli.py          — cross-cutting
  core/                             — tests for src/wavern/core/
  gui/                              — tests for src/wavern/gui/
  visualizations/                   — tests for src/wavern/visualizations/
  presets/                          — tests for src/wavern/presets/
```

Each test file begins with a `WHAT THIS TESTS` / `Does NOT test` docstring header.

## Conventions

- Type hints on all function signatures
- Google-style docstrings
- Conventional commits (`feat:`, `fix:`, `refactor:`)
- Errors must be handled explicitly — no silent failures
- Prefer composition over inheritance

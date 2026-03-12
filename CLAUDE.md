# Wavern — Project Instructions for AI Agents

## Quick Reference

- **Language**: Python 3.12 (strict: `>=3.12,<3.13`)
- **Package manager**: `uv` (not pip)
- **Build**: hatchling, src layout (`src/wavern/`)
- **Tests**: `uv run pytest tests/ -v` (all tests must pass)
- **Run GUI**: `uv run wavern gui`
- **Lint**: ruff, line-length 100

## Architecture

### Source Layout

```
src/wavern/
  core/           — audio_loader, audio_analyzer, audio_player, renderer, export, timeline
  visualizations/ — base ABC + 5 built-in types + registry
  presets/        — pydantic schema + manager + defaults/*.json
  shaders/        — GLSL 3.3 core (.vert/.frag)
  gui/            — PySide6 widgets (main_window, gl_widget, settings_panel, etc.)
  utils/          — color, math_utils
  cli.py          — click CLI entry point
  app.py          — QApplication bootstrap
```

### Key Design Decisions

- **Renderer is display-agnostic**: `Renderer.render_frame(frame, fbo, resolution)` works identically for GUI preview (QOpenGLWidget) and headless export (standalone context). Never add GUI awareness to the renderer.
- **Visualization lifecycle**: `__init__(ctx, params)` → `initialize()` → `render()` per frame → `cleanup()`. GPU resources are created in `initialize()`, not `__init__`.
- **FrameAnalysis dataclass** is the universal audio contract. All visualizations receive it — never pass raw audio to render methods.
- **Preset** is a pydantic model. Built-in presets ship as JSON in `presets/defaults/`, user presets live at `~/.config/wavern/presets/`.

### Critical Patterns

**Safe uniform setting**: GLSL compilers strip unused uniforms. Always use `self._set_uniform(prog, name, value)` and `self._write_uniform(prog, name, data)` from `AbstractVisualization` — never raw `prog[name].value = ...` which throws `KeyError` if optimized out.

**Uniform arrays**: moderngl doesn't support bracket-indexed uniform access (`prog["u_arr[0]"]`). Upload entire arrays via `prog["u_arr"].write(numpy_buffer.tobytes())`.

**Large uniform arrays**: Arrays over ~256 floats can exceed GPU constant register limits. Use textures instead (see `waveform.py` which uses a 2D texture of shape `(N, 1)` for waveform data).

**Signal blocking in Qt**: When rebuilding the settings panel programmatically, block signals on combo boxes (`blockSignals(True)`) before populating/setting values to prevent cascading `params_changed` emissions that wipe preset params.

**Renderer type change detection**: `renderer.update_params()` auto-detects when `visualization_type` changed and calls `set_preset()` internally. Callers don't need to distinguish param updates from type switches.

**Transparent export**: Background type "none" exports with alpha via VP9/WebM (`yuva420p`). H.264/MP4 does not support alpha. VP9 requires `-b:v 0` for CRF mode + `-speed 4 -row-mt 1` for reasonable encode time.

## Adding a New Visualization

1. Create `src/wavern/visualizations/my_viz.py`
2. Subclass `AbstractVisualization`, set `NAME`, `DISPLAY_NAME`, `DESCRIPTION`, `CATEGORY`, `PARAM_SCHEMA`
3. Implement `initialize()`, `render()`, `cleanup()` — use `_set_uniform`/`_write_uniform` for all uniforms
4. Apply `@register` decorator
5. Add import to `src/wavern/visualizations/__init__.py`
6. Create matching preset JSON in `src/wavern/presets/defaults/`

## Conventions

- Type hints on all function signatures
- Google-style docstrings
- Conventional commits (`feat:`, `fix:`, `refactor:`)
- Errors must be handled explicitly — no silent failures
- Prefer composition over inheritance

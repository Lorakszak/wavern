# wavern/visualizations — Agent Guide

## Purpose
Self-contained visualization plugins. Each file is one visualization type.

## File Inventory
| File | Name | Status |
|---|---|---|
| `base.py` | `AbstractVisualization` ABC + `image_mixin.py` helper | — |
| `registry.py` | `@register` decorator + `get_visualization()` / `list_visualizations()` | — |
| `spectrum_bars.py` | `SpectrumBars` | Stable |
| `circular_spectrum.py` | `CircularSpectrum` | Stable |
| `rect_spectrum.py` | `RectSpectrum` | Stable |
| `waveform.py` | `Waveform` | Beta |
| `particles.py` | `Particles` | Stable |
| `smoky_waves.py` | `SmokyWaves` | Beta |
| `lissajous.py` | `Lissajous` | Alpha |
| `radial_waveform.py` | `RadialWaveform` | Alpha |
| `spectrogram.py` | `Spectrogram` | Alpha |
| `oscilloscope.py` | `CRTOscilloscope` | Beta |
| `tunnel.py` | `Tunnel` | Alpha |

## Visualization Lifecycle
```
__init__(ctx, params)   — store ctx + params, NO GPU work here
initialize()            — create VAO, VBO, shader program, textures
render(frame, fbo, res) — upload uniforms, draw; called every frame
cleanup()               — release GPU resources
```
GPU resources **must** be created in `initialize()`, not `__init__`.

## Required Class Attributes
```python
NAME = "my_viz"                     # snake_case, unique, used in preset JSON
DISPLAY_NAME = "My Visualization"   # shown in UI
DESCRIPTION = "One sentence."
CATEGORY = "stable"                 # "stable" | "beta" | "alpha"
PARAM_SCHEMA: dict[str, dict]       # parameter definitions (see below)
```

## PARAM_SCHEMA Format
```python
PARAM_SCHEMA = {
    "bar_count": {"type": "int", "default": 64, "min": 8, "max": 256, "label": "Bar Count"},
    "color_mode": {"type": "str", "default": "solid", "options": ["solid", "gradient"]},
    "glow": {"type": "bool", "default": False},
    "color": {"type": "color", "default": "#ff6600"},
    "image": {"type": "file", "default": ""},
}
```

## Adding a New Visualization
1. Create `src/wavern/visualizations/my_viz.py`
2. Subclass `AbstractVisualization`, set all required class attributes
3. Implement `initialize()`, `render()`, `cleanup()`
4. Apply `@register` decorator
5. Add import to `src/wavern/visualizations/__init__.py`
6. Create `src/wavern/presets/defaults/my_viz_default.json`
7. Add tests: registration, PARAM_SCHEMA types, preset JSON validity

## Safe Uniform Helpers (from AbstractVisualization)
- `self._set_uniform(prog, "name", value)` — safe scalar/vector set
- `self._write_uniform(prog, "name", np_array)` — safe buffer write

For arrays >256 floats, use a texture instead of a uniform array (see `waveform.py`).

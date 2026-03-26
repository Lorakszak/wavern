# Global Post-Processing Effects — Design Spec

**Date**: 2026-03-26
**Branch**: `feat/audio-reactive-backgrounds`
**Scope**: Phase 2 — global post-processing (vignette, chromatic aberration, glitch, film grain)
**Depends on**: Phase 1 (background effects + audio reactivity) — already merged to this branch

## Overview

Add four global post-processing effects applied to the fully composited frame: vignette, chromatic aberration, glitch (with type selector), and film grain. Each effect has manual intensity control and optional audio-reactive modulation (reusing Phase 1's `AudioReactiveConfig`). A single placement toggle controls whether effects apply before or after text/video overlays.

## Architecture: Global Effects Pass

### Current pipeline (after Phase 1)

```
background.frag → [bg_effects.frag] → main FBO
viz layers → layer FBOs → composite.frag → main FBO
video overlay → main FBO
text overlay → main FBO
```

### New pipeline (when any global effect is enabled)

**`apply_stage = "before_overlays"` (default):**
```
background.frag → [bg_effects.frag] → main FBO
viz layers → layer FBOs → composite.frag → main FBO
── global_effects.frag: main FBO → intermediate FBO → main FBO ──
video overlay → main FBO
text overlay → main FBO
```

**`apply_stage = "after_overlays"`:**
```
background.frag → [bg_effects.frag] → main FBO
viz layers → layer FBOs → composite.frag → main FBO
video overlay → main FBO
text overlay → main FBO
── global_effects.frag: main FBO → intermediate FBO → main FBO ──
```

### Optimization

When no global effects are enabled, the renderer skips the global effects pass entirely — zero overhead for presets that don't use it.

## Schema Changes

All new models go in `src/wavern/presets/schema.py`.

### New models

```python
class VignetteEffect(BaseModel):
    """Vignette effect with shape selection."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    shape: str = Field(
        default="circular",
        pattern=r"^(circular|rectangular|diamond)$",
    )
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class ChromaticAberrationEffect(BaseModel):
    """Chromatic aberration with direction mode."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    direction: str = Field(
        default="radial",
        pattern=r"^(radial|linear)$",
    )
    angle: float = Field(default=0.0, ge=0.0, le=360.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class GlitchEffect(BaseModel):
    """Glitch effect with type selection."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    type: str = Field(
        default="scanline",
        pattern=r"^(scanline|block|digital)$",
    )
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class FilmGrainEffect(BaseModel):
    """Animated film grain noise overlay."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class GlobalEffects(BaseModel):
    """Container for all global post-processing effects."""

    apply_stage: str = Field(
        default="before_overlays",
        pattern=r"^(before_overlays|after_overlays)$",
    )
    vignette: VignetteEffect = Field(default_factory=VignetteEffect)
    chromatic_aberration: ChromaticAberrationEffect = Field(
        default_factory=ChromaticAberrationEffect
    )
    glitch: GlitchEffect = Field(default_factory=GlitchEffect)
    film_grain: FilmGrainEffect = Field(default_factory=FilmGrainEffect)
```

### Modified models

**Preset** — add global effects container:

```python
class Preset(BaseModel):
    # ... all existing fields unchanged ...
    global_effects: GlobalEffects = Field(default_factory=GlobalEffects)
```

### Backward compatibility

All new fields have defaults via `default_factory`. Old preset JSON files without `global_effects` load correctly through pydantic's default filling. No migration code needed.

### Effect intensity semantics

| Effect | intensity=0.0 | intensity=0.5 | intensity=1.0 |
|--------|--------------|---------------|---------------|
| **vignette** | No darkening | Moderate edge darkening | Heavy, reaches near center |
| **chromatic aberration** | No offset | ~10px RGB offset | ~20px RGB offset |
| **glitch** | No displacement | Moderate artifacts | Heavy corruption |
| **film grain** | No grain | Subtle grain | Heavy grain |

## Audio Reactivity

Reuses Phase 1's existing infrastructure entirely:

- `AudioReactiveConfig` model (enabled/source/sensitivity)
- `AUDIO_SOURCE_MAP` in `renderer.py` (amplitude/bass/beat/mid/treble)
- `_resolve_effect_intensity()` function — each global effect model has an `intensity` and `audio` field matching the `BackgroundEffect` interface

For effects that only have `enabled`, `intensity`, and `audio`, `_resolve_effect_intensity` works directly. For effects with extra fields (shape, direction, type), the extra fields are config-only — they don't affect intensity resolution.

Note: `_resolve_effect_intensity` takes a `BackgroundEffect`, not a generic protocol. Since the global effect models (`VignetteEffect`, `GlitchEffect`, etc.) have the same `intensity` and `audio` fields but are different types, the renderer needs a small adapter. Two options:

**Option chosen**: Add a `_resolve_global_effect_intensity()` function that takes `intensity: float` and `audio: AudioReactiveConfig` directly, avoiding coupling to `BackgroundEffect`. This is a 3-line function that duplicates the logic but keeps the types clean.

```python
def _resolve_global_effect_intensity(
    intensity: float, audio: AudioReactiveConfig, frame: FrameAnalysis,
) -> float:
    """Compute final intensity for a global effect, optionally modulated by audio."""
    if audio.enabled:
        audio_val = AUDIO_SOURCE_MAP[audio.source](frame)
        return min(max(intensity * audio_val * audio.sensitivity, 0.0), 1.0)
    return intensity
```

## Shader: `global_effects.frag`

New file: `src/wavern/shaders/global_effects.frag`

Vertex shader: reuses `common.vert` (same fullscreen quad).

### Uniforms

```glsl
uniform sampler2D u_scene;        // intermediate FBO texture (composited frame)
uniform vec2 u_resolution;        // viewport size in pixels
uniform float u_time;             // animation time (for glitch + grain)

// Vignette
uniform int u_vignette_enabled;
uniform float u_vignette_intensity;
uniform int u_vignette_shape;     // 0=circular, 1=rectangular, 2=diamond

// Chromatic aberration
uniform int u_chromatic_enabled;
uniform float u_chromatic_intensity;
uniform int u_chromatic_direction; // 0=radial, 1=linear
uniform float u_chromatic_angle;   // radians (for linear mode)

// Glitch
uniform int u_glitch_enabled;
uniform float u_glitch_intensity;
uniform int u_glitch_type;        // 0=scanline, 1=block, 2=digital

// Film grain
uniform int u_grain_enabled;
uniform float u_grain_intensity;
```

### Effect implementations

**Glitch (runs first — displaces pixels):**

All three types use a pseudo-random hash function seeded by `u_time` for animation.

- **Scanline** (`type=0`): Divide screen into horizontal bands. Each band has a random horizontal offset proportional to intensity. Bands change each frame based on time.
- **Block** (`type=1`): Random rectangular regions get displaced and optionally color-shifted. Block positions and sizes change per frame.
- **Digital** (`type=2`): Scanline displacement (like type 0) plus per-displaced-line RGB channel separation — red channel offset left, blue offset right.

**Chromatic aberration (runs second — splits channels):**

- **Radial** (`direction=0`): Offset direction points from center toward current pixel. R channel offset outward by `intensity * 20.0` pixels, B channel offset inward, G stays.
- **Linear** (`direction=1`): Offset direction defined by `u_chromatic_angle`. R offset forward along angle, B offset backward.

**Film grain (runs third — noise overlay):**

Animated pseudo-random noise using `fract(sin(dot(...)))` hash, seeded by `gl_FragCoord.xy + u_time`. Luminance-weighted: `grain *= (1.0 - 0.5 * luma)` so grain is more visible in shadows/midtones than highlights (like real film). Added to RGB as `color.rgb += grain * u_grain_intensity`.

**Vignette (runs last — darkens edges):**

- **Circular** (`shape=0`): `factor = smoothstep(outer, inner, length(uv - 0.5))` where `outer` and `inner` are derived from intensity.
- **Rectangular** (`shape=1`): Same pattern but using `max(abs(uv.x - 0.5), abs(uv.y - 0.5))` as distance.
- **Diamond** (`shape=2`): Same pattern but using `abs(uv.x - 0.5) + abs(uv.y - 0.5)` as distance (Manhattan/L1 norm).

Multiply RGB by the vignette factor. Alpha unchanged.

### Application order

```glsl
void main() {
    vec2 uv = v_texcoord;
    vec4 color;

    // 1. Glitch (displaces pixels, must sample texture)
    if (u_glitch_enabled == 1 && u_glitch_intensity > 0.001) {
        color = apply_glitch(uv);
    } else {
        color = texture(u_scene, uv);
    }

    // 2. Chromatic aberration (splits RGB channels)
    if (u_chromatic_enabled == 1 && u_chromatic_intensity > 0.001) {
        color = apply_chromatic(uv, color);
    }

    // 3. Film grain (noise overlay)
    if (u_grain_enabled == 1 && u_grain_intensity > 0.001) {
        color = apply_grain(color);
    }

    // 4. Vignette (edge darkening, last)
    if (u_vignette_enabled == 1) {
        color = apply_vignette(uv, color);
    }

    fragColor = color;
}
```

Glitch runs first because it displaces pixels (needs raw texture sampling). Chromatic aberration next because it also samples with offsets. Film grain adds noise. Vignette last because it's a multiplicative darkening that should affect the final result.

Note on chromatic aberration + glitch interaction: `apply_chromatic` always re-samples from `u_scene` at the original UV with per-channel offsets. When glitch is also enabled, the glitch displacement and chromatic offset are independent — chromatic aberration operates on the pre-glitch image. This is acceptable because (a) the visual result is still compelling and (b) glitch's "digital" mode already includes its own color separation for the displaced lines.

## Renderer Changes

File: `src/wavern/core/renderer.py`

### New resources (lazily created)

```python
# Global effects pass
self._global_effects_fbo: moderngl.Framebuffer | None = None
self._global_effects_texture: moderngl.Texture | None = None
self._global_effects_prog: moderngl.Program | None = None
self._global_effects_vao: moderngl.VertexArray | None = None
self._global_effects_vbo: moderngl.Buffer | None = None
self._global_effects_resolution: tuple[int, int] | None = None
```

### New methods

- `_ensure_global_effects_pass()` — lazily create the shader program, VBO, VAO (same pattern as `_ensure_bg_effects_pass()`).
- `_ensure_global_effects_fbo(resolution)` — create/resize intermediate FBO (same pattern as `_ensure_bg_effects_fbo()`).
- `_release_global_effects_fbo()` — release intermediate FBO resources.
- `_set_global_effects_uniforms(global_effects, frame, resolution)` — resolve intensities via `_resolve_global_effect_intensity()`, upload all uniforms using safe `if key in prog` pattern.
- `_resolve_global_effect_intensity(intensity, audio, frame)` — module-level function, compute final intensity with optional audio modulation.
- `_any_global_effect_enabled(global_effects)` — module-level function, returns True if any effect has `enabled=True`.

### Modified methods

**`render_frame()`** — insert global effects pass at the correct point based on `apply_stage`:

```python
def render_frame(self, frame, fbo, resolution, preview=False):
    # ... clear, background, layers, compositing (unchanged) ...

    # Global effects — before overlays
    if (self._preset is not None
        and self._preset.global_effects.apply_stage == "before_overlays"
        and _any_global_effect_enabled(self._preset.global_effects)):
        self._apply_global_effects(fbo, frame, resolution)

    # Video overlay (unchanged)
    # Text overlay (unchanged)

    # Global effects — after overlays
    if (self._preset is not None
        and self._preset.global_effects.apply_stage == "after_overlays"
        and _any_global_effect_enabled(self._preset.global_effects)):
        self._apply_global_effects(fbo, frame, resolution)
```

**`_apply_global_effects(fbo, frame, resolution)`** — new private method:
1. Copy current `fbo` content to intermediate FBO (render fbo's texture to intermediate, or blit)
2. Bind intermediate texture, set uniforms
3. Render fullscreen quad back to `fbo`

Implementation detail: Unlike the bg_effects pass where we can redirect the background render to an intermediate FBO *before* it hits the main FBO, here the main FBO already has content. We need to:
1. Blit main FBO → intermediate FBO (using `ctx.copy_framebuffer`)
2. Clear main FBO
3. Bind intermediate texture → render effects quad → main FBO

Alternatively, use the same approach as bg_effects: render to intermediate, then render back. But since the main FBO already has content, we use `ctx.copy_framebuffer(dst=_global_effects_fbo, src=fbo)` to capture it.

**`cleanup()`** — add global effects resource cleanup (same pattern as bg_effects).

## GUI Changes

### New file: `src/wavern/gui/panels/global_effects_section.py`

A new section widget following the section widget pattern from `panels/CLAUDE.md`. This keeps it self-contained rather than overloading `background_section.py`.

```python
class GlobalEffectsSection(QWidget):
    effects_changed = Signal()

    def build(self, preset: Preset) -> None: ...
    def update_values(self, preset: Preset) -> None: ...
```

### Controls layout

```
Global Effects
├── Apply Stage: [Before Overlays ▾]
├── Vignette
│   ├── Enable: [checkbox]
│   ├── Intensity: [0.5] (DragSpinBox 0.0-1.0)
│   ├── Shape: [circular ▾]
│   ├── Audio Reactive: [checkbox]
│   ├── Audio Source: [amplitude ▾]     (visible when reactive checked)
│   └── Sensitivity: [1.0]             (visible when reactive checked)
├── Chromatic Aberration
│   ├── Enable: [checkbox]
│   ├── Intensity: [0.5]
│   ├── Direction: [radial ▾]
│   ├── Angle: [0.0]                   (visible when direction=linear)
│   ├── Audio Reactive: [checkbox]
│   ├── Audio Source: [amplitude ▾]
│   └── Sensitivity: [1.0]
├── Glitch
│   ├── Enable: [checkbox]
│   ├── Intensity: [0.5]
│   ├── Type: [scanline ▾]
│   ├── Audio Reactive: [checkbox]
│   ├── Audio Source: [amplitude ▾]
│   └── Sensitivity: [1.0]
└── Film Grain
    ├── Enable: [checkbox]
    ├── Intensity: [0.5]
    ├── Audio Reactive: [checkbox]
    ├── Audio Source: [amplitude ▾]
    └── Sensitivity: [1.0]
```

### Integration into VisualPanel

In `visual_panel.py`, add the global effects section as a new `CollapsibleSection` between the Background section and the Video Overlay section. This positions it logically — after the background/layer visuals, before overlays:

```python
# --- Global Effects ---
self._global_effects_section = CollapsibleSection("Global Effects")
self._global_effects_widget = GlobalEffectsSection()
self._global_effects_widget.effects_changed.connect(self._emit_update)
self._global_effects_widget.build(preset)
self._global_effects_section.set_content(self._global_effects_widget)
self._content_layout.addWidget(self._global_effects_section)
```

### Reuse from Phase 1

The `_build_audio_reactive_controls` helper lives on `BackgroundSection`. For the global effects section to reuse it, either:

**Option chosen**: Extract it to a free function in a shared module (e.g., `gui/panels/audio_reactive_controls.py`) or duplicate it as a method on `GlobalEffectsSection`. Given it's ~60 lines, duplication is acceptable — but extraction is cleaner. Extract to a standalone function that takes a form layout and returns the widget tuple. Both `BackgroundSection` and `GlobalEffectsSection` call it.

### Signal flow

```
effect widget changed
  → GlobalEffectsSection._on_effects_changed()
  → updates preset.global_effects.*
  → emits effects_changed
  → VisualPanel._emit_update()
  → MainWindow._apply_preset()
  → Renderer.update_params()
```

No changes to `MainWindow` API — global effects flow through the existing `Preset` object.

## Testing

### Schema tests (`tests/presets/test_preset_schema.py`)

- `VignetteEffect`: defaults, shape validation (circular/rectangular/diamond), invalid shape rejected
- `ChromaticAberrationEffect`: defaults, direction validation, angle range
- `GlitchEffect`: defaults, type validation (scanline/block/digital)
- `FilmGrainEffect`: defaults, intensity range
- `GlobalEffects`: all 4 effects present with defaults, apply_stage validation
- `Preset` backward compat: old JSON without `global_effects` loads with defaults
- `Preset` round-trip: full preset with global effects serializes and deserializes

### Renderer tests (`tests/core/test_global_effects.py`)

- `_resolve_global_effect_intensity`: manual-only returns base intensity
- `_resolve_global_effect_intensity`: audio reactive returns modulated value
- `_resolve_global_effect_intensity`: result clamped to [0.0, 1.0]
- `_any_global_effect_enabled`: returns False when all disabled, True when any enabled

### Existing tests

All built-in preset JSON files have validation tests — they continue to pass via pydantic default filling.

### Not tested (manual testing only)

Shader compilation, FBO rendering, visual output — requires GPU context not available in CI.

## Files Changed

| File | Change |
|------|--------|
| `src/wavern/presets/schema.py` | Add `VignetteEffect`, `ChromaticAberrationEffect`, `GlitchEffect`, `FilmGrainEffect`, `GlobalEffects`; add `global_effects` to `Preset` |
| `src/wavern/shaders/global_effects.frag` | New file — vignette, chromatic aberration, glitch (3 types), film grain |
| `src/wavern/core/renderer.py` | Add global effects FBO/shader resources, `_apply_global_effects`, placement logic in `render_frame` |
| `src/wavern/gui/panels/global_effects_section.py` | New file — global effects UI section |
| `src/wavern/gui/panels/audio_reactive_controls.py` | New file — extracted `build_audio_reactive_controls` free function |
| `src/wavern/gui/panels/background_section.py` | Refactor to use extracted audio reactive controls helper |
| `src/wavern/gui/panels/visual_panel.py` | Add global effects section between Background and Video Overlay |
| `tests/presets/test_preset_schema.py` | Tests for new schema models and backward compat |
| `tests/core/test_global_effects.py` | Tests for intensity resolution and effect enabled check |

# Global Post-Processing Effects — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four global post-processing effects (vignette, chromatic aberration, glitch, film grain) applied to the fully composited frame, with per-effect audio reactivity and a placement toggle (before/after overlays).

**Architecture:** Single-shader post-processing pass using an intermediate FBO. The renderer copies the composited frame to an intermediate texture, runs `global_effects.frag` with audio-modulated uniforms, and outputs back to the main FBO. Placement is controlled by `apply_stage` ("before_overlays" / "after_overlays") which determines the insertion point in `render_frame`. When no effects are enabled, the pass is skipped entirely.

**Tech Stack:** Python 3.12, pydantic v2, moderngl, GLSL 3.30 core, PySide6, pytest

**Spec:** `docs/superpowers/specs/2026-03-26-global-post-processing-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/wavern/presets/schema.py` | Modify | Add `VignetteEffect`, `ChromaticAberrationEffect`, `GlitchEffect`, `FilmGrainEffect`, `GlobalEffects`; add `global_effects` to `Preset` |
| `src/wavern/shaders/global_effects.frag` | Create | Post-processing shader: vignette (3 shapes), chromatic aberration (radial/linear), glitch (3 types), film grain |
| `src/wavern/core/renderer.py` | Modify | Global effects FBO/shader resources, `_apply_global_effects`, placement logic in `render_frame` |
| `src/wavern/gui/panels/global_effects_section.py` | Create | Global effects UI section with per-effect controls |
| `src/wavern/gui/panels/visual_panel.py` | Modify | Add global effects section between Background and Video Overlay |
| `tests/presets/test_preset_schema.py` | Modify | Tests for new schema models and backward compat |
| `tests/core/test_global_effects.py` | Create | Tests for intensity resolution and effect enabled check |

---

### Task 1: Schema Models

**Files:**
- Modify: `src/wavern/presets/schema.py:100-219`
- Test: `tests/presets/test_preset_schema.py`

- [ ] **Step 1: Write failing tests for new schema models**

Add to the imports at the top of `tests/presets/test_preset_schema.py` (merge with existing import block on lines 15-27):

```python
from wavern.presets.schema import (
    AudioReactiveConfig,
    BackgroundConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
    BlendMode,
    ChromaticAberrationEffect,
    ColorStop,
    FilmGrainEffect,
    GlobalEffects,
    GlitchEffect,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
    VignetteEffect,
    VisualizationLayer,
)
```

Add these test classes at the END of the file:

```python
class TestVignetteEffect:
    def test_defaults(self):
        v = VignetteEffect()
        assert v.enabled is False
        assert v.intensity == 0.5
        assert v.shape == "circular"
        assert v.audio.enabled is False

    def test_valid_shapes(self):
        for shape in ("circular", "rectangular", "diamond"):
            v = VignetteEffect(shape=shape)
            assert v.shape == shape

    def test_invalid_shape(self):
        with pytest.raises(ValidationError):
            VignetteEffect(shape="triangle")

    def test_intensity_range(self):
        VignetteEffect(intensity=0.0)
        VignetteEffect(intensity=1.0)
        with pytest.raises(ValidationError):
            VignetteEffect(intensity=-0.1)
        with pytest.raises(ValidationError):
            VignetteEffect(intensity=1.1)


class TestChromaticAberrationEffect:
    def test_defaults(self):
        c = ChromaticAberrationEffect()
        assert c.enabled is False
        assert c.intensity == 0.5
        assert c.direction == "radial"
        assert c.angle == 0.0

    def test_valid_directions(self):
        for direction in ("radial", "linear"):
            c = ChromaticAberrationEffect(direction=direction)
            assert c.direction == direction

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(direction="spiral")

    def test_angle_range(self):
        ChromaticAberrationEffect(angle=0.0)
        ChromaticAberrationEffect(angle=360.0)
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(angle=-1.0)
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(angle=361.0)

    def test_full_construction(self):
        c = ChromaticAberrationEffect(
            enabled=True,
            intensity=0.8,
            direction="linear",
            angle=45.0,
            audio=AudioReactiveConfig(enabled=True, source="treble"),
        )
        assert c.direction == "linear"
        assert c.angle == 45.0
        assert c.audio.source == "treble"


class TestGlitchEffect:
    def test_defaults(self):
        g = GlitchEffect()
        assert g.enabled is False
        assert g.intensity == 0.5
        assert g.type == "scanline"

    def test_valid_types(self):
        for t in ("scanline", "block", "digital"):
            g = GlitchEffect(type=t)
            assert g.type == t

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            GlitchEffect(type="vhs")


class TestFilmGrainEffect:
    def test_defaults(self):
        f = FilmGrainEffect()
        assert f.enabled is False
        assert f.intensity == 0.5
        assert f.audio.enabled is False

    def test_intensity_range(self):
        FilmGrainEffect(intensity=0.0)
        FilmGrainEffect(intensity=1.0)
        with pytest.raises(ValidationError):
            FilmGrainEffect(intensity=-0.1)
        with pytest.raises(ValidationError):
            FilmGrainEffect(intensity=1.1)


class TestGlobalEffects:
    def test_defaults(self):
        ge = GlobalEffects()
        assert ge.apply_stage == "before_overlays"
        assert ge.vignette.enabled is False
        assert ge.chromatic_aberration.enabled is False
        assert ge.glitch.enabled is False
        assert ge.film_grain.enabled is False

    def test_valid_apply_stages(self):
        for stage in ("before_overlays", "after_overlays"):
            ge = GlobalEffects(apply_stage=stage)
            assert ge.apply_stage == stage

    def test_invalid_apply_stage(self):
        with pytest.raises(ValidationError):
            GlobalEffects(apply_stage="during_overlays")

    def test_individual_effect_enabled(self):
        ge = GlobalEffects(
            glitch=GlitchEffect(enabled=True, intensity=0.7, type="block"),
        )
        assert ge.glitch.enabled is True
        assert ge.glitch.type == "block"
        assert ge.vignette.enabled is False


class TestGlobalEffectsBackwardCompat:
    def test_old_preset_without_global_effects(self):
        """Old preset JSON without global_effects loads with defaults."""
        preset = Preset(
            name="Legacy Preset",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        assert preset.global_effects.apply_stage == "before_overlays"
        assert preset.global_effects.vignette.enabled is False
        assert preset.global_effects.glitch.enabled is False

    def test_preset_roundtrip_with_global_effects(self):
        preset = Preset(
            name="Global FX Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            global_effects=GlobalEffects(
                apply_stage="after_overlays",
                vignette=VignetteEffect(enabled=True, intensity=0.8, shape="diamond"),
                chromatic_aberration=ChromaticAberrationEffect(
                    enabled=True, direction="linear", angle=90.0,
                    audio=AudioReactiveConfig(enabled=True, source="treble", sensitivity=2.0),
                ),
                glitch=GlitchEffect(enabled=True, type="digital"),
                film_grain=FilmGrainEffect(enabled=True, intensity=0.3),
            ),
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.global_effects.apply_stage == "after_overlays"
        assert restored.global_effects.vignette.shape == "diamond"
        assert restored.global_effects.chromatic_aberration.direction == "linear"
        assert restored.global_effects.chromatic_aberration.angle == 90.0
        assert restored.global_effects.chromatic_aberration.audio.source == "treble"
        assert restored.global_effects.glitch.type == "digital"
        assert restored.global_effects.film_grain.intensity == 0.3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/presets/test_preset_schema.py -v -k "TestVignetteEffect or TestChromaticAberrationEffect or TestGlitchEffect or TestFilmGrainEffect or TestGlobalEffects" 2>&1 | head -30`

Expected: `ImportError` — `VignetteEffect`, `GlitchEffect`, etc. do not exist yet.

- [ ] **Step 3: Implement schema models**

In `src/wavern/presets/schema.py`, add five new models after `BackgroundEffects` (after line 61, before `BackgroundMovement`):

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
        default_factory=ChromaticAberrationEffect,
    )
    glitch: GlitchEffect = Field(default_factory=GlitchEffect)
    film_grain: FilmGrainEffect = Field(default_factory=FilmGrainEffect)
```

Add `global_effects` field to `Preset` (after `video_overlay` field, currently line 209):

```python
    global_effects: GlobalEffects = Field(default_factory=GlobalEffects)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/presets/test_preset_schema.py -v -k "TestVignetteEffect or TestChromaticAberrationEffect or TestGlitchEffect or TestFilmGrainEffect or TestGlobalEffects"`

Expected: All tests PASS.

- [ ] **Step 5: Run all existing preset tests to confirm no regressions**

Run: `uv run pytest tests/presets/ -v`

Expected: All tests PASS (including `test_all_presets.py` which validates every built-in JSON file).

- [ ] **Step 6: Commit**

```bash
git add src/wavern/presets/schema.py tests/presets/test_preset_schema.py
git commit -m "$(cat <<'EOF'
feat(schema): add global post-processing effect models

Add VignetteEffect, ChromaticAberrationEffect, GlitchEffect,
FilmGrainEffect, GlobalEffects pydantic models. Extend Preset
with global_effects container. All fields default cleanly for
backward compat with existing presets.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Global Effects Shader

**Files:**
- Create: `src/wavern/shaders/global_effects.frag`

- [ ] **Step 1: Create the global effects shader**

Create `src/wavern/shaders/global_effects.frag`:

```glsl
#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_scene;
uniform vec2 u_resolution;
uniform float u_time;

// Vignette
uniform int u_vignette_enabled;
uniform float u_vignette_intensity;
uniform int u_vignette_shape;     // 0=circular, 1=rectangular, 2=diamond

// Chromatic aberration
uniform int u_chromatic_enabled;
uniform float u_chromatic_intensity;
uniform int u_chromatic_direction; // 0=radial, 1=linear
uniform float u_chromatic_angle;   // radians

// Glitch
uniform int u_glitch_enabled;
uniform float u_glitch_intensity;
uniform int u_glitch_type;        // 0=scanline, 1=block, 2=digital

// Film grain
uniform int u_grain_enabled;
uniform float u_grain_intensity;

// --- Pseudo-random hash ---

float hash(float n) {
    return fract(sin(n) * 43758.5453123);
}

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

// --- Glitch ---

vec4 apply_glitch_scanline(vec2 uv) {
    float time_seed = floor(u_time * 8.0);
    float line_height = 0.02 + 0.03 * hash(time_seed * 3.7);
    float band = floor(uv.y / line_height);
    float rand_val = hash(band * 13.37 + time_seed);

    // Only displace some bands (probability scales with intensity)
    if (rand_val < u_glitch_intensity * 0.6) {
        float offset = (hash(band * 7.13 + time_seed * 2.0) - 0.5) * u_glitch_intensity * 0.15;
        uv.x = fract(uv.x + offset);
    }
    return texture(u_scene, uv);
}

vec4 apply_glitch_block(vec2 uv) {
    float time_seed = floor(u_time * 6.0);
    vec4 color = texture(u_scene, uv);

    // Generate a few random blocks per frame
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 block_pos = vec2(hash(fi * 17.3 + time_seed), hash(fi * 31.7 + time_seed * 1.3));
        vec2 block_size = vec2(
            0.05 + 0.15 * hash(fi * 43.1 + time_seed),
            0.01 + 0.04 * hash(fi * 59.3 + time_seed)
        );

        if (uv.x > block_pos.x && uv.x < block_pos.x + block_size.x &&
            uv.y > block_pos.y && uv.y < block_pos.y + block_size.y) {
            float prob = hash(fi * 73.1 + time_seed);
            if (prob < u_glitch_intensity * 0.8) {
                vec2 displaced = uv + vec2(
                    (hash(fi * 97.1 + time_seed) - 0.5) * u_glitch_intensity * 0.2,
                    0.0
                );
                color = texture(u_scene, fract(displaced));
                // Optional color shift
                float shift = (hash(fi * 101.3 + time_seed) - 0.5) * u_glitch_intensity * 0.3;
                color.r = texture(u_scene, fract(displaced + vec2(shift, 0.0))).r;
            }
        }
    }
    return color;
}

vec4 apply_glitch_digital(vec2 uv) {
    float time_seed = floor(u_time * 8.0);
    float line_height = 0.02 + 0.03 * hash(time_seed * 3.7);
    float band = floor(uv.y / line_height);
    float rand_val = hash(band * 13.37 + time_seed);

    vec2 displaced_uv = uv;
    float rgb_split = 0.0;

    if (rand_val < u_glitch_intensity * 0.6) {
        float offset = (hash(band * 7.13 + time_seed * 2.0) - 0.5) * u_glitch_intensity * 0.15;
        displaced_uv.x = fract(uv.x + offset);
        rgb_split = u_glitch_intensity * 0.01 * hash(band * 11.0 + time_seed);
    }

    // RGB channel separation on displaced lines
    vec4 color;
    color.r = texture(u_scene, displaced_uv + vec2(rgb_split, 0.0)).r;
    color.g = texture(u_scene, displaced_uv).g;
    color.b = texture(u_scene, displaced_uv - vec2(rgb_split, 0.0)).b;
    color.a = texture(u_scene, displaced_uv).a;
    return color;
}

vec4 apply_glitch(vec2 uv) {
    if (u_glitch_type == 1) {
        return apply_glitch_block(uv);
    } else if (u_glitch_type == 2) {
        return apply_glitch_digital(uv);
    }
    return apply_glitch_scanline(uv);
}

// --- Chromatic Aberration ---

vec4 apply_chromatic(vec2 uv, vec4 center_color) {
    vec2 texel = 1.0 / u_resolution;
    float offset_px = u_chromatic_intensity * 20.0;
    vec2 offset_dir;

    if (u_chromatic_direction == 1) {
        // Linear: direction from angle
        offset_dir = vec2(cos(u_chromatic_angle), sin(u_chromatic_angle));
    } else {
        // Radial: direction from center to current pixel
        offset_dir = normalize(uv - 0.5);
    }

    vec2 offset = offset_dir * offset_px * texel;

    float r = texture(u_scene, uv + offset).r;
    float g = center_color.g;
    float b = texture(u_scene, uv - offset).b;
    return vec4(r, g, b, center_color.a);
}

// --- Film Grain ---

vec4 apply_grain(vec4 color) {
    vec2 noise_coord = gl_FragCoord.xy + vec2(u_time * 1000.0, u_time * 573.0);
    float noise = hash2(noise_coord) * 2.0 - 1.0;

    // Luminance-weighted: more visible in shadows/midtones
    float luma = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
    noise *= (1.0 - 0.5 * luma);

    color.rgb += vec3(noise * u_grain_intensity * 0.3);
    color.rgb = clamp(color.rgb, 0.0, 1.0);
    return color;
}

// --- Vignette ---

vec4 apply_vignette(vec2 uv, vec4 color) {
    vec2 centered = uv - 0.5;
    float dist;

    if (u_vignette_shape == 1) {
        // Rectangular: Chebyshev distance
        dist = max(abs(centered.x), abs(centered.y)) * 2.0;
    } else if (u_vignette_shape == 2) {
        // Diamond: Manhattan distance
        dist = (abs(centered.x) + abs(centered.y)) * 1.5;
    } else {
        // Circular: Euclidean distance
        dist = length(centered) * 2.0;
    }

    // Map intensity to vignette reach: 0=no darkening, 1=heavy
    float inner = 1.0 - u_vignette_intensity * 0.8;
    float outer = inner + 0.3;
    float factor = smoothstep(outer, inner, dist);
    color.rgb *= factor;
    return color;
}

// --- Main ---

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

- [ ] **Step 2: Verify shader file is loadable**

Run: `uv run python -c "from wavern.shaders import load_shader; s = load_shader('global_effects.frag'); print(f'Loaded {len(s)} chars')"`

Expected: Prints `Loaded <N> chars` without errors.

- [ ] **Step 3: Commit**

```bash
git add src/wavern/shaders/global_effects.frag
git commit -m "$(cat <<'EOF'
feat(shaders): add global_effects.frag for post-processing

Vignette (circular/rectangular/diamond), chromatic aberration
(radial/linear), glitch (scanline/block/digital), and animated
film grain. Each effect gated by enable flag + intensity uniform.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Renderer — Global Intensity Resolution & Helper Functions

**Files:**
- Modify: `src/wavern/core/renderer.py:79-113`
- Create: `tests/core/test_global_effects.py`

- [ ] **Step 1: Write failing tests**

Create `tests/core/test_global_effects.py`:

```python
"""Tests for global post-processing effects intensity resolution.

WHAT THIS TESTS:
- _resolve_global_effect_intensity returns base intensity when audio disabled
- _resolve_global_effect_intensity returns modulated value when audio enabled
- _resolve_global_effect_intensity clamps result to [0.0, 1.0]
- _any_global_effect_enabled detects enabled effects
Does NOT test: shader compilation, FBO rendering, GUI
"""

import numpy as np
import pytest

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.renderer import (
    _any_global_effect_enabled,
    _resolve_global_effect_intensity,
)
from wavern.presets.schema import (
    AudioReactiveConfig,
    ChromaticAberrationEffect,
    FilmGrainEffect,
    GlobalEffects,
    GlitchEffect,
    VignetteEffect,
)


def _make_frame(
    amplitude_envelope: float = 0.0,
    beat_intensity: float = 0.0,
    band_envelopes: dict[str, float] | None = None,
) -> FrameAnalysis:
    """Create a FrameAnalysis with controllable audio fields."""
    return FrameAnalysis(
        timestamp=1.0,
        waveform=np.zeros(2048, dtype=np.float32),
        fft_magnitudes=np.zeros(1024, dtype=np.float32),
        fft_frequencies=np.linspace(0, 22050, 1024, dtype=np.float32),
        frequency_bands={
            k: 0.0
            for k in (
                "sub_bass", "bass", "low_mid", "mid",
                "upper_mid", "presence", "brilliance",
            )
        },
        amplitude=0.0,
        peak=0.0,
        beat=False,
        beat_intensity=beat_intensity,
        spectral_centroid=0.0,
        spectral_flux=0.0,
        amplitude_envelope=amplitude_envelope,
        band_envelopes=band_envelopes or {},
    )


class TestResolveGlobalEffectIntensity:
    def test_manual_only(self):
        audio = AudioReactiveConfig()
        frame = _make_frame()
        assert _resolve_global_effect_intensity(0.7, audio, frame) == 0.7

    def test_audio_reactive(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0)
        frame = _make_frame(amplitude_envelope=0.8)
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == pytest.approx(0.5 * 0.8 * 1.0)

    def test_audio_reactive_with_sensitivity(self):
        audio = AudioReactiveConfig(enabled=True, source="bass", sensitivity=3.0)
        frame = _make_frame(band_envelopes={"bass": 0.6})
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == pytest.approx(0.5 * 0.6 * 3.0)

    def test_clamps_to_one(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=5.0)
        frame = _make_frame(amplitude_envelope=1.0)
        result = _resolve_global_effect_intensity(1.0, audio, frame)
        assert result == 1.0

    def test_clamps_to_zero(self):
        audio = AudioReactiveConfig(enabled=True, source="amplitude", sensitivity=1.0)
        frame = _make_frame(amplitude_envelope=0.0)
        result = _resolve_global_effect_intensity(0.5, audio, frame)
        assert result == 0.0


class TestAnyGlobalEffectEnabled:
    def test_none_enabled(self):
        effects = GlobalEffects()
        assert _any_global_effect_enabled(effects) is False

    def test_vignette_enabled(self):
        effects = GlobalEffects(vignette=VignetteEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_chromatic_enabled(self):
        effects = GlobalEffects(
            chromatic_aberration=ChromaticAberrationEffect(enabled=True),
        )
        assert _any_global_effect_enabled(effects) is True

    def test_glitch_enabled(self):
        effects = GlobalEffects(glitch=GlitchEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_grain_enabled(self):
        effects = GlobalEffects(film_grain=FilmGrainEffect(enabled=True))
        assert _any_global_effect_enabled(effects) is True

    def test_multiple_enabled(self):
        effects = GlobalEffects(
            vignette=VignetteEffect(enabled=True),
            glitch=GlitchEffect(enabled=True),
        )
        assert _any_global_effect_enabled(effects) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_global_effects.py -v 2>&1 | head -20`

Expected: `ImportError` — `_resolve_global_effect_intensity`, `_any_global_effect_enabled` do not exist yet.

- [ ] **Step 3: Implement functions in renderer.py**

Add imports to the schema import block (line 16-28) — merge with existing:

```python
from wavern.presets.schema import (
    AudioReactiveConfig,
    BackgroundConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
    BlendMode,
    ColorStop,
    GlobalEffects,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
    VisualizationLayer,
    VisualizationParams,
)
```

Add after `_any_bg_effect_enabled` (after line 113), before the `Renderer` class:

```python
def _resolve_global_effect_intensity(
    intensity: float, audio: AudioReactiveConfig, frame: FrameAnalysis,
) -> float:
    """Compute final intensity for a global effect, optionally modulated by audio."""
    if audio.enabled:
        audio_val = AUDIO_SOURCE_MAP[audio.source](frame)
        return min(max(intensity * audio_val * audio.sensitivity, 0.0), 1.0)
    return intensity


def _any_global_effect_enabled(effects: GlobalEffects) -> bool:
    """Return True if any global effect is enabled."""
    return (
        effects.vignette.enabled
        or effects.chromatic_aberration.enabled
        or effects.glitch.enabled
        or effects.film_grain.enabled
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_global_effects.py -v`

Expected: All 11 tests PASS.

- [ ] **Step 5: Run linting**

Run: `uv run ruff check src/wavern/core/renderer.py tests/core/test_global_effects.py`

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/wavern/core/renderer.py tests/core/test_global_effects.py
git commit -m "$(cat <<'EOF'
feat(renderer): add global effect intensity resolution and enabled check

Module-level _resolve_global_effect_intensity and
_any_global_effect_enabled functions for the global post-processing
pipeline. Fully tested.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Renderer — Global Effects Pipeline

**Files:**
- Modify: `src/wavern/core/renderer.py`

- [ ] **Step 1: Add global effects resources to `__init__`**

In `Renderer.__init__`, add after the bg_effects block (after line 160, the `self._bg_effects_resolution` line):

```python
        # Global effects pass (created lazily)
        self._global_effects_fbo: moderngl.Framebuffer | None = None
        self._global_effects_texture: moderngl.Texture | None = None
        self._global_effects_prog: moderngl.Program | None = None
        self._global_effects_vao: moderngl.VertexArray | None = None
        self._global_effects_vbo: moderngl.Buffer | None = None
        self._global_effects_resolution: tuple[int, int] | None = None
```

- [ ] **Step 2: Add `_ensure_global_effects_pass` method**

Add after `_release_bg_effects_fbo` (the bg_effects methods). Find the end of the bg_effects methods and add:

```python
    def _ensure_global_effects_pass(self) -> None:
        """Lazily create the global effects shader program and fullscreen quad."""
        if self._global_effects_prog is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("global_effects.frag")
        self._global_effects_prog = self.ctx.program(
            vertex_shader=vert_src, fragment_shader=frag_src,
        )

        vertices = np.array(
            [
                -1.0, -1.0, 0.0, 0.0,
                 1.0, -1.0, 1.0, 0.0,
                -1.0,  1.0, 0.0, 1.0,
                 1.0,  1.0, 1.0, 1.0,
            ],
            dtype="f4",
        )
        self._global_effects_vbo = self.ctx.buffer(vertices.tobytes())
        self._global_effects_vao = self.ctx.vertex_array(
            self._global_effects_prog,
            [(self._global_effects_vbo, "2f 2f", "in_position", "in_texcoord")],
        )
```

- [ ] **Step 3: Add `_ensure_global_effects_fbo` and `_release_global_effects_fbo` methods**

Add immediately after:

```python
    def _ensure_global_effects_fbo(self, resolution: tuple[int, int]) -> None:
        """Create or resize the intermediate FBO for the global effects pass."""
        if self._global_effects_resolution == resolution and self._global_effects_fbo is not None:
            return
        self._release_global_effects_fbo()
        self._global_effects_texture = self.ctx.texture(resolution, 4)
        self._global_effects_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._global_effects_fbo = self.ctx.framebuffer(
            color_attachments=[self._global_effects_texture],
        )
        self._global_effects_resolution = resolution

    def _release_global_effects_fbo(self) -> None:
        """Release the global effects intermediate FBO."""
        if self._global_effects_fbo is not None:
            self._global_effects_fbo.release()
            self._global_effects_fbo = None
        if self._global_effects_texture is not None:
            self._global_effects_texture.release()
            self._global_effects_texture = None
        self._global_effects_resolution = None
```

- [ ] **Step 4: Add `_set_global_effects_uniforms` method**

Add after `_set_bg_effects_uniforms`:

```python
    def _set_global_effects_uniforms(
        self, effects: GlobalEffects, frame: FrameAnalysis, resolution: tuple[int, int],
    ) -> None:
        """Upload global effects uniforms to the shader."""
        prog = self._global_effects_prog
        if prog is None:
            return

        if "u_resolution" in prog:
            prog["u_resolution"].value = (float(resolution[0]), float(resolution[1]))  # type: ignore[reportAttributeAccessIssue]
        if "u_time" in prog:
            prog["u_time"].value = frame.timestamp  # type: ignore[reportAttributeAccessIssue]

        # Vignette
        v = effects.vignette
        v_intensity = _resolve_global_effect_intensity(v.intensity, v.audio, frame)
        if "u_vignette_enabled" in prog:
            prog["u_vignette_enabled"].value = int(v.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_vignette_intensity" in prog:
            prog["u_vignette_intensity"].value = v_intensity  # type: ignore[reportAttributeAccessIssue]
        shape_map = {"circular": 0, "rectangular": 1, "diamond": 2}
        if "u_vignette_shape" in prog:
            prog["u_vignette_shape"].value = shape_map.get(v.shape, 0)  # type: ignore[reportAttributeAccessIssue]

        # Chromatic aberration
        ca = effects.chromatic_aberration
        ca_intensity = _resolve_global_effect_intensity(ca.intensity, ca.audio, frame)
        if "u_chromatic_enabled" in prog:
            prog["u_chromatic_enabled"].value = int(ca.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_intensity" in prog:
            prog["u_chromatic_intensity"].value = ca_intensity  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_direction" in prog:
            prog["u_chromatic_direction"].value = 1 if ca.direction == "linear" else 0  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_angle" in prog:
            prog["u_chromatic_angle"].value = math.radians(ca.angle)  # type: ignore[reportAttributeAccessIssue]

        # Glitch
        g = effects.glitch
        g_intensity = _resolve_global_effect_intensity(g.intensity, g.audio, frame)
        if "u_glitch_enabled" in prog:
            prog["u_glitch_enabled"].value = int(g.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_glitch_intensity" in prog:
            prog["u_glitch_intensity"].value = g_intensity  # type: ignore[reportAttributeAccessIssue]
        type_map = {"scanline": 0, "block": 1, "digital": 2}
        if "u_glitch_type" in prog:
            prog["u_glitch_type"].value = type_map.get(g.type, 0)  # type: ignore[reportAttributeAccessIssue]

        # Film grain
        fg = effects.film_grain
        fg_intensity = _resolve_global_effect_intensity(fg.intensity, fg.audio, frame)
        if "u_grain_enabled" in prog:
            prog["u_grain_enabled"].value = int(fg.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_grain_intensity" in prog:
            prog["u_grain_intensity"].value = fg_intensity  # type: ignore[reportAttributeAccessIssue]
```

- [ ] **Step 5: Add `_apply_global_effects` method**

Add after `_set_global_effects_uniforms`:

```python
    def _apply_global_effects(
        self, fbo: moderngl.Framebuffer, frame: FrameAnalysis, resolution: tuple[int, int],
    ) -> None:
        """Run the global effects pass: copy fbo to intermediate, apply effects, write back."""
        assert self._preset is not None
        self._ensure_global_effects_pass()
        self._ensure_global_effects_fbo(resolution)
        assert self._global_effects_fbo is not None
        assert self._global_effects_texture is not None
        assert self._global_effects_prog is not None
        assert self._global_effects_vao is not None

        # Copy current fbo content to intermediate
        self.ctx.copy_framebuffer(dst=self._global_effects_fbo, src=fbo)

        # Render effects pass back to main fbo
        fbo.use()
        self.ctx.viewport = (0, 0, resolution[0], resolution[1])
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        self._global_effects_texture.use(location=0)
        if "u_scene" in self._global_effects_prog:
            self._global_effects_prog["u_scene"].value = 0  # type: ignore[reportAttributeAccessIssue]

        self._set_global_effects_uniforms(
            self._preset.global_effects, frame, resolution,
        )

        self._global_effects_vao.render(moderngl.TRIANGLE_STRIP)
```

- [ ] **Step 6: Modify `render_frame` to insert global effects pass**

In the `render_frame` method, insert global effects logic. Find the compositing `_composite_vao.render` call (currently around line 717) and the overlay blocks. Replace the section from after compositing through the end of overlays with:

```python
            self._composite_vao.render(moderngl.TRIANGLE_STRIP)

        # Global effects — before overlays
        if (
            self._preset is not None
            and self._preset.global_effects.apply_stage == "before_overlays"
            and _any_global_effect_enabled(self._preset.global_effects)
        ):
            self._apply_global_effects(fbo, frame, resolution)

        # Render video overlay on top of visualization
        skip_overlay = preview and self.skip_overlay_preview
        if self._overlay_video_source is not None and not skip_overlay:
            try:
                self._render_overlay(frame)
            except Exception as e:
                logger.error("Video overlay render error: %s", e)

        # Render text overlay on top
        if self._text_overlay is not None:
            try:
                self._text_overlay.render(fbo, resolution, frame.timestamp)
            except Exception as e:
                logger.error("Text overlay render error: %s", e)

        # Global effects — after overlays
        if (
            self._preset is not None
            and self._preset.global_effects.apply_stage == "after_overlays"
            and _any_global_effect_enabled(self._preset.global_effects)
        ):
            self._apply_global_effects(fbo, frame, resolution)
```

- [ ] **Step 7: Update `cleanup` method**

Add global effects resource cleanup to the `cleanup` method. After the bg_effects cleanup block (after line 912):

```python
        self._release_global_effects_fbo()
        if self._global_effects_vao is not None:
            self._global_effects_vao.release()
            self._global_effects_vao = None
        if self._global_effects_vbo is not None:
            self._global_effects_vbo.release()
            self._global_effects_vbo = None
        if self._global_effects_prog is not None:
            self._global_effects_prog.release()
            self._global_effects_prog = None
```

- [ ] **Step 8: Run linting and type checker**

Run: `uv run ruff check src/wavern/core/renderer.py && uv run pyright src/wavern/core/renderer.py`

Expected: No new errors.

- [ ] **Step 9: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add src/wavern/core/renderer.py
git commit -m "$(cat <<'EOF'
feat(renderer): global post-processing effects pipeline

Intermediate FBO, shader program, uniform upload, and
_apply_global_effects method. Placement logic in render_frame
supports before_overlays and after_overlays stages. Pass skipped
when no effects are enabled.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: GUI — Global Effects Section

**Files:**
- Create: `src/wavern/gui/panels/global_effects_section.py`

- [ ] **Step 1: Create the global effects section widget**

Create `src/wavern/gui/panels/global_effects_section.py`:

```python
"""Global post-processing effects section — vignette, chromatic aberration, glitch, film grain."""

import logging
from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import (
    AudioReactiveConfig,
    ChromaticAberrationEffect,
    FilmGrainEffect,
    GlobalEffects,
    GlitchEffect,
    Preset,
    VignetteEffect,
)

logger = logging.getLogger(__name__)


class GlobalEffectsSection(QWidget):
    """Controls for global post-processing effects applied to the composited frame."""

    effects_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding: bool = False

    def build(self, preset: Preset) -> None:
        """Build the global effects UI for the given preset."""
        self._preset = preset
        self._rebuilding = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)

        effects = preset.global_effects

        # Apply stage combo
        stage_form = QFormLayout()
        self._stage_combo = NoScrollComboBox()
        self._stage_combo.blockSignals(True)
        self._stage_combo.addItem("Before Overlays", "before_overlays")
        self._stage_combo.addItem("After Overlays", "after_overlays")
        idx = self._stage_combo.findData(effects.apply_stage)
        if idx >= 0:
            self._stage_combo.setCurrentIndex(idx)
        self._stage_combo.blockSignals(False)
        self._stage_combo.currentIndexChanged.connect(self._on_effects_changed)
        stage_form.addRow("Apply:", self._stage_combo)
        layout.addLayout(stage_form)

        # Vignette
        self._build_vignette(layout, effects.vignette)

        # Chromatic Aberration
        self._build_chromatic(layout, effects.chromatic_aberration)

        # Glitch
        self._build_glitch(layout, effects.glitch)

        # Film Grain
        self._build_film_grain(layout, effects.film_grain)

        layout.addStretch()
        self._rebuilding = False

    def _build_vignette(self, layout: QVBoxLayout, effect: VignetteEffect) -> None:
        """Build vignette controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._vignette_enable = QCheckBox("Vignette")
        self._vignette_enable.setChecked(effect.enabled)
        self._vignette_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._vignette_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._vignette_intensity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
            description="Controls how far inward the darkening reaches.",
            default_value=0.5,
        )
        self._vignette_intensity.setValue(effect.intensity)
        self._vignette_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._vignette_intensity)

        self._vignette_shape = NoScrollComboBox()
        self._vignette_shape.blockSignals(True)
        for shape_name, shape_val in [("Circular", "circular"), ("Rectangular", "rectangular"), ("Diamond", "diamond")]:
            self._vignette_shape.addItem(shape_name, shape_val)
        idx = self._vignette_shape.findData(effect.shape)
        if idx >= 0:
            self._vignette_shape.setCurrentIndex(idx)
        self._vignette_shape.blockSignals(False)
        self._vignette_shape.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Shape:", self._vignette_shape)

        (
            self._vignette_audio_cb,
            self._vignette_audio_source,
            self._vignette_audio_sensitivity,
            self._vignette_audio_source_label,
            self._vignette_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout, effect.audio, self._on_effects_changed,
        )

        sub.setVisible(effect.enabled)
        self._vignette_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_chromatic(self, layout: QVBoxLayout, effect: ChromaticAberrationEffect) -> None:
        """Build chromatic aberration controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._chromatic_enable = QCheckBox("Chromatic Aberration")
        self._chromatic_enable.setChecked(effect.enabled)
        self._chromatic_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._chromatic_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._chromatic_intensity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
            description="Controls the RGB channel offset distance.",
            default_value=0.5,
        )
        self._chromatic_intensity.setValue(effect.intensity)
        self._chromatic_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._chromatic_intensity)

        self._chromatic_direction = NoScrollComboBox()
        self._chromatic_direction.blockSignals(True)
        self._chromatic_direction.addItem("Radial", "radial")
        self._chromatic_direction.addItem("Linear", "linear")
        idx = self._chromatic_direction.findData(effect.direction)
        if idx >= 0:
            self._chromatic_direction.setCurrentIndex(idx)
        self._chromatic_direction.blockSignals(False)
        self._chromatic_direction.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Direction:", self._chromatic_direction)

        self._chromatic_angle = DragSpinBox(
            minimum=0.0, maximum=360.0, step=1.0, decimals=1,
            description="Angle for linear chromatic aberration direction.",
            default_value=0.0,
        )
        self._chromatic_angle.setValue(effect.angle)
        self._chromatic_angle.valueChanged.connect(self._on_effects_changed)
        self._chromatic_angle_label = QLabel("Angle:")
        sub_layout.addRow(self._chromatic_angle_label, self._chromatic_angle)

        # Show angle only for linear direction
        is_linear = effect.direction == "linear"
        self._chromatic_angle_label.setVisible(is_linear)
        self._chromatic_angle.setVisible(is_linear)

        def _toggle_angle_visibility(_idx: int) -> None:
            is_lin = self._chromatic_direction.currentData() == "linear"
            self._chromatic_angle_label.setVisible(is_lin)
            self._chromatic_angle.setVisible(is_lin)

        self._chromatic_direction.currentIndexChanged.connect(_toggle_angle_visibility)

        (
            self._chromatic_audio_cb,
            self._chromatic_audio_source,
            self._chromatic_audio_sensitivity,
            self._chromatic_audio_source_label,
            self._chromatic_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout, effect.audio, self._on_effects_changed,
        )

        sub.setVisible(effect.enabled)
        self._chromatic_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_glitch(self, layout: QVBoxLayout, effect: GlitchEffect) -> None:
        """Build glitch controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._glitch_enable = QCheckBox("Glitch")
        self._glitch_enable.setChecked(effect.enabled)
        self._glitch_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._glitch_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._glitch_intensity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
            description="Controls the severity of glitch artifacts.",
            default_value=0.5,
        )
        self._glitch_intensity.setValue(effect.intensity)
        self._glitch_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._glitch_intensity)

        self._glitch_type = NoScrollComboBox()
        self._glitch_type.blockSignals(True)
        for type_name, type_val in [("Scanline", "scanline"), ("Block", "block"), ("Digital", "digital")]:
            self._glitch_type.addItem(type_name, type_val)
        idx = self._glitch_type.findData(effect.type)
        if idx >= 0:
            self._glitch_type.setCurrentIndex(idx)
        self._glitch_type.blockSignals(False)
        self._glitch_type.currentIndexChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Type:", self._glitch_type)

        (
            self._glitch_audio_cb,
            self._glitch_audio_source,
            self._glitch_audio_sensitivity,
            self._glitch_audio_source_label,
            self._glitch_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout, effect.audio, self._on_effects_changed,
        )

        sub.setVisible(effect.enabled)
        self._glitch_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    def _build_film_grain(self, layout: QVBoxLayout, effect: FilmGrainEffect) -> None:
        """Build film grain controls."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)

        self._grain_enable = QCheckBox("Film Grain")
        self._grain_enable.setChecked(effect.enabled)
        self._grain_enable.toggled.connect(self._on_effects_changed)
        form.addRow(self._grain_enable)

        sub = QWidget()
        sub_layout = QFormLayout(sub)
        sub_layout.setContentsMargins(12, 0, 0, 0)

        self._grain_intensity = DragSpinBox(
            minimum=0.0, maximum=1.0, step=0.05, decimals=2,
            description="Controls the visibility of the film grain overlay.",
            default_value=0.5,
        )
        self._grain_intensity.setValue(effect.intensity)
        self._grain_intensity.valueChanged.connect(self._on_effects_changed)
        sub_layout.addRow("Intensity:", self._grain_intensity)

        (
            self._grain_audio_cb,
            self._grain_audio_source,
            self._grain_audio_sensitivity,
            self._grain_audio_source_label,
            self._grain_audio_sens_wrapper,
        ) = self._build_audio_reactive_controls(
            sub_layout, effect.audio, self._on_effects_changed,
        )

        sub.setVisible(effect.enabled)
        self._grain_enable.toggled.connect(sub.setVisible)

        form.addRow(sub)
        layout.addLayout(form)

    # -- Audio reactive controls (same pattern as background_section.py) --

    def _wrap_with_buttons(
        self,
        widget: QWidget,
        description: str = "",
        default_callback: Callable[[], None] | None = None,
        default_label: str = "",
    ) -> QWidget:
        """Wrap a widget with optional reset-to-default and help buttons."""
        if not description and default_callback is None:
            return widget
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(widget, stretch=1)
        if default_callback is not None:
            btn = QPushButton(default_label or "Reset")
            btn.setFixedWidth(40)
            btn.setObjectName("ColorControlBtn")
            btn.clicked.connect(default_callback)
            row.addWidget(btn)
        if description:
            row.addWidget(make_help_button(description))
        return container

    def _build_audio_reactive_controls(
        self,
        form: QFormLayout,
        audio: AudioReactiveConfig,
        on_changed: Callable[[], None],
    ) -> tuple[QCheckBox, NoScrollComboBox, DragSpinBox, QLabel, QWidget]:
        """Build audio-reactive controls: checkbox, source combo, sensitivity."""
        reactive_cb = QCheckBox()
        reactive_cb.setChecked(audio.enabled)
        reactive_cb.toggled.connect(on_changed)
        wrapped_reactive = self._wrap_with_buttons(
            reactive_cb,
            description=(
                "When enabled, the effect intensity is modulated\n"
                "by the selected audio signal in real time."
            ),
            default_callback=lambda: reactive_cb.setChecked(False),
            default_label="off",
        )
        form.addRow("Audio Reactive:", wrapped_reactive)

        source_combo = NoScrollComboBox()
        source_combo.blockSignals(True)
        for source in ("amplitude", "bass", "beat", "mid", "treble"):
            source_combo.addItem(source, source)
        idx = source_combo.findData(audio.source)
        if idx >= 0:
            source_combo.setCurrentIndex(idx)
        source_combo.blockSignals(False)
        source_combo.currentIndexChanged.connect(on_changed)
        source_label = QLabel("Audio Source:")
        form.addRow(source_label, source_combo)

        sensitivity_spin = DragSpinBox(
            minimum=0.1, maximum=5.0, step=0.1, decimals=1,
            description="Multiplier for the audio signal strength.",
            default_value=1.0,
        )
        sensitivity_spin.setValue(audio.sensitivity)
        sensitivity_spin.valueChanged.connect(on_changed)
        sens_wrapper = self._wrap_with_buttons(
            sensitivity_spin,
            description="Multiplier for the audio signal strength.",
            default_callback=lambda: sensitivity_spin.setValue(1.0),
            default_label="1.0",
        )
        sens_label = QLabel("Sensitivity:")
        form.addRow(sens_label, sens_wrapper)

        source_label.setVisible(audio.enabled)
        source_combo.setVisible(audio.enabled)
        sens_label.setVisible(audio.enabled)
        sens_wrapper.setVisible(audio.enabled)

        def _toggle_audio_visibility(checked: bool) -> None:
            source_label.setVisible(checked)
            source_combo.setVisible(checked)
            sens_label.setVisible(checked)
            sens_wrapper.setVisible(checked)

        reactive_cb.toggled.connect(_toggle_audio_visibility)

        return reactive_cb, source_combo, sensitivity_spin, source_label, sens_wrapper

    # -- Signal handlers --

    def _on_effects_changed(self) -> None:
        """Collect all effect widget values into the preset and emit signal."""
        if self._preset is None or self._rebuilding:
            return

        self._preset.global_effects.apply_stage = (
            self._stage_combo.currentData() or "before_overlays"
        )

        # Vignette
        self._preset.global_effects.vignette = VignetteEffect(
            enabled=self._vignette_enable.isChecked(),
            intensity=self._vignette_intensity.value(),
            shape=self._vignette_shape.currentData() or "circular",
            audio=AudioReactiveConfig(
                enabled=self._vignette_audio_cb.isChecked(),
                source=self._vignette_audio_source.currentData() or "amplitude",
                sensitivity=self._vignette_audio_sensitivity.value(),
            ),
        )

        # Chromatic aberration
        self._preset.global_effects.chromatic_aberration = ChromaticAberrationEffect(
            enabled=self._chromatic_enable.isChecked(),
            intensity=self._chromatic_intensity.value(),
            direction=self._chromatic_direction.currentData() or "radial",
            angle=self._chromatic_angle.value(),
            audio=AudioReactiveConfig(
                enabled=self._chromatic_audio_cb.isChecked(),
                source=self._chromatic_audio_source.currentData() or "amplitude",
                sensitivity=self._chromatic_audio_sensitivity.value(),
            ),
        )

        # Glitch
        self._preset.global_effects.glitch = GlitchEffect(
            enabled=self._glitch_enable.isChecked(),
            intensity=self._glitch_intensity.value(),
            type=self._glitch_type.currentData() or "scanline",
            audio=AudioReactiveConfig(
                enabled=self._glitch_audio_cb.isChecked(),
                source=self._glitch_audio_source.currentData() or "amplitude",
                sensitivity=self._glitch_audio_sensitivity.value(),
            ),
        )

        # Film grain
        self._preset.global_effects.film_grain = FilmGrainEffect(
            enabled=self._grain_enable.isChecked(),
            intensity=self._grain_intensity.value(),
            audio=AudioReactiveConfig(
                enabled=self._grain_audio_cb.isChecked(),
                source=self._grain_audio_source.currentData() or "amplitude",
                sensitivity=self._grain_audio_sensitivity.value(),
            ),
        )

        self.effects_changed.emit()

    def update_values(self, preset: Preset) -> None:
        """Sync widget values without rebuilding."""
        self._preset = preset
        self._rebuilding = True
        effects = preset.global_effects

        self._stage_combo.blockSignals(True)
        idx = self._stage_combo.findData(effects.apply_stage)
        if idx >= 0:
            self._stage_combo.setCurrentIndex(idx)
        self._stage_combo.blockSignals(False)

        # Vignette
        self._sync_effect_widgets(
            effects.vignette,
            self._vignette_enable, self._vignette_intensity,
            self._vignette_audio_cb, self._vignette_audio_source,
            self._vignette_audio_sensitivity,
        )
        self._vignette_shape.blockSignals(True)
        idx = self._vignette_shape.findData(effects.vignette.shape)
        if idx >= 0:
            self._vignette_shape.setCurrentIndex(idx)
        self._vignette_shape.blockSignals(False)

        # Chromatic aberration
        self._sync_effect_widgets(
            effects.chromatic_aberration,
            self._chromatic_enable, self._chromatic_intensity,
            self._chromatic_audio_cb, self._chromatic_audio_source,
            self._chromatic_audio_sensitivity,
        )
        self._chromatic_direction.blockSignals(True)
        idx = self._chromatic_direction.findData(effects.chromatic_aberration.direction)
        if idx >= 0:
            self._chromatic_direction.setCurrentIndex(idx)
        self._chromatic_direction.blockSignals(False)
        self._chromatic_angle.blockSignals(True)
        self._chromatic_angle.setValue(effects.chromatic_aberration.angle)
        self._chromatic_angle.blockSignals(False)

        # Glitch
        self._sync_effect_widgets(
            effects.glitch,
            self._glitch_enable, self._glitch_intensity,
            self._glitch_audio_cb, self._glitch_audio_source,
            self._glitch_audio_sensitivity,
        )
        self._glitch_type.blockSignals(True)
        idx = self._glitch_type.findData(effects.glitch.type)
        if idx >= 0:
            self._glitch_type.setCurrentIndex(idx)
        self._glitch_type.blockSignals(False)

        # Film grain
        self._sync_effect_widgets(
            effects.film_grain,
            self._grain_enable, self._grain_intensity,
            self._grain_audio_cb, self._grain_audio_source,
            self._grain_audio_sensitivity,
        )

        self._rebuilding = False

    def _sync_effect_widgets(
        self,
        effect: VignetteEffect | ChromaticAberrationEffect | GlitchEffect | FilmGrainEffect,
        enable_cb: QCheckBox,
        intensity_spin: DragSpinBox,
        audio_cb: QCheckBox,
        audio_source: NoScrollComboBox,
        audio_sensitivity: DragSpinBox,
    ) -> None:
        """Sync common effect widgets with blockSignals."""
        enable_cb.blockSignals(True)
        enable_cb.setChecked(effect.enabled)
        enable_cb.blockSignals(False)
        intensity_spin.blockSignals(True)
        intensity_spin.setValue(effect.intensity)
        intensity_spin.blockSignals(False)
        audio_cb.blockSignals(True)
        audio_cb.setChecked(effect.audio.enabled)
        audio_cb.blockSignals(False)
        audio_source.blockSignals(True)
        idx = audio_source.findData(effect.audio.source)
        if idx >= 0:
            audio_source.setCurrentIndex(idx)
        audio_source.blockSignals(False)
        audio_sensitivity.blockSignals(True)
        audio_sensitivity.setValue(effect.audio.sensitivity)
        audio_sensitivity.blockSignals(False)
```

- [ ] **Step 2: Run linting**

Run: `uv run ruff check src/wavern/gui/panels/global_effects_section.py && uv run ruff format src/wavern/gui/panels/global_effects_section.py`

Expected: Clean or auto-fixed.

- [ ] **Step 3: Commit**

```bash
git add src/wavern/gui/panels/global_effects_section.py
git commit -m "$(cat <<'EOF'
feat(gui): add global effects section widget

Vignette (shape), chromatic aberration (direction/angle), glitch
(type), and film grain controls. Each with enable/intensity and
audio-reactive sub-controls. Apply stage toggle for before/after
overlays.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: GUI — Integrate into VisualPanel

**Files:**
- Modify: `src/wavern/gui/panels/visual_panel.py`

- [ ] **Step 1: Add import**

Add to the imports at the top of `visual_panel.py` (after the other panel imports on line 12-16):

```python
from wavern.gui.panels.global_effects_section import GlobalEffectsSection
```

- [ ] **Step 2: Add section widget reference in `__init__`**

In `VisualPanel.__init__`, add after `self._fade_section_widget` (line 54):

```python
        self._global_effects_widget: GlobalEffectsSection | None = None
```

- [ ] **Step 3: Add global effects section in `set_preset`**

In `set_preset`, add the global effects section between the Background section and the Video Overlay section. Find the `# --- Video Overlay ---` comment (line 159) and insert BEFORE it:

```python
        # --- Global Effects ---
        self._global_effects_section_container = CollapsibleSection("Global Effects")
        self._global_effects_widget = GlobalEffectsSection()
        self._global_effects_widget.effects_changed.connect(self._emit_update)
        self._global_effects_widget.build(preset)
        self._global_effects_section_container.set_content(self._global_effects_widget)
        self._content_layout.addWidget(self._global_effects_section_container)

```

- [ ] **Step 4: Add `update_values` delegation**

In `update_values`, add after `self._bg_section_widget.update_values(...)` (line 261) and before `self._overlay_section_widget.update_values(...)`:

```python
        if self._global_effects_widget is not None:
            self._global_effects_widget.update_values(preset)
```

- [ ] **Step 5: Run linting**

Run: `uv run ruff check src/wavern/gui/panels/visual_panel.py`

Expected: No errors.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/wavern/gui/panels/visual_panel.py
git commit -m "$(cat <<'EOF'
feat(gui): integrate global effects section into visual panel

Global Effects section added between Background and Video Overlay
in the sidebar. Syncs via update_values for dual-sidebar support.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Final Verification

**Files:** All modified files

- [ ] **Step 1: Run full linting**

Run: `uv run ruff check src/ tests/`

- [ ] **Step 2: Run type checker**

Run: `uv run pyright src/`

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 4: Verify the app launches**

Run: `uv run wavern gui`

Expected: App opens. A "Global Effects" collapsible section appears in the sidebar between Background and Video Overlay. Enable vignette → edges darken. Enable glitch → artifacts appear. Toggle apply stage → effects move before/after overlays. Audio reactive → source/sensitivity controls appear.

- [ ] **Step 5: Commit any final fixes if needed**

Only if the verification steps above revealed issues that needed fixing.

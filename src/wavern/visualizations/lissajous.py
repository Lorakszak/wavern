"""Lissajous visualization — phase-portrait of the audio waveform."""

from typing import Any, ClassVar

import math

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

# Phase-portrait Lissajous: X = waveform[i], Y = waveform[i + delay].
#
# Performance note: the segment loop is O(N) per pixel. With N ≤ MAX_SAMPLES
# and the inner symmetry loop ≤ MAX_SYMMETRY, total iterations per pixel =
# N * symmetry. At 256 * 4 = 1024 iterations and ~2M pixels the GPU handles
# this comfortably on modern hardware (texture cache helps since both textures
# are tiny and fully reused across the pixel grid).
_LISSAJOUS_FRAG = """
#version 330 core

#define PI          3.14159265359
#define MAX_SAMPLES  512
#define MAX_SYMMETRY 8

uniform sampler2D u_ch_x;
uniform sampler2D u_ch_y;
uniform int   u_sample_count;
uniform vec2  u_resolution;
uniform float u_line_thickness;
uniform float u_glow_intensity;
uniform float u_amplitude_scale;
uniform float u_amplitude;
uniform float u_beat_intensity;
uniform vec3  u_colors[8];
uniform int   u_color_count;
uniform vec2  u_offset;
uniform float u_scale;
uniform float u_rotation;
// New controls
uniform float u_tail_fade;
uniform float u_spin_speed;
uniform float u_time;
uniform int   u_symmetry;
uniform bool  u_mirror_x;

in vec2 v_texcoord;
out vec4 fragColor;

vec3 get_color(float t) {
    if (u_color_count <= 1) return u_colors[0];
    float idx_f = t * float(u_color_count - 1);
    int idx = int(floor(idx_f));
    float fract_t = idx_f - float(idx);
    idx = clamp(idx, 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], fract_t);
}

float seg_dist(vec2 p, vec2 a, vec2 b, out float seg_t) {
    vec2 ab = b - a;
    float len2 = dot(ab, ab);
    if (len2 < 1e-10) {
        seg_t = 0.0;
        return length(p - a);
    }
    seg_t = clamp(dot(p - a, ab) / len2, 0.0, 1.0);
    return length(p - (a + seg_t * ab));
}

mat2 rot2(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c, -s, s, c);
}

void main() {
    vec2 uv = v_texcoord;

    // Standard viewport transform
    uv -= 0.5;
    uv -= u_offset;
    uv /= u_scale;
    uv = rot2(u_rotation) * uv;
    uv += 0.5;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    // Square space: 1 unit = 1 screen-height pixel.
    // Equal X/Y signal amplitudes produce a circle, not an ellipse.
    float aspect = u_resolution.x / u_resolution.y;
    vec2 p = vec2((uv.x - 0.5) * aspect, uv.y - 0.5);

    // Mirror X before symmetry (folds left half onto right — doubles patterns).
    if (u_mirror_x) p.x = abs(p.x);

    // Precompute symmetry-rotated pixel positions once, outside segment loop.
    vec2 p_sym[MAX_SYMMETRY];
    int sym_count = clamp(u_symmetry, 1, MAX_SYMMETRY);
    float sym_step = 2.0 * PI / float(sym_count);
    for (int s = 0; s < MAX_SYMMETRY; s++) {
        if (s >= sym_count) break;
        p_sym[s] = rot2(sym_step * float(s)) * p;
    }

    // Spin: rotate the curve itself over time (not the viewport).
    mat2 spin = rot2(u_time * u_spin_speed);

    float beat_boost = 1.0 + u_beat_intensity * 0.5 + u_amplitude * 0.15;

    float min_dist     = 1e9;
    float min_t_curve  = 0.0;
    int N = min(u_sample_count, MAX_SAMPLES);

    for (int i = 1; i < N; i++) {
        float fi0 = (float(i - 1) + 0.5) / float(N);
        float fi1 = (float(i)     + 0.5) / float(N);

        // Scale 0.45: full-scale signal fits within ~90% of screen height.
        float s0 = u_amplitude_scale * 0.45;
        vec2 pa = spin * vec2(
            texture(u_ch_x, vec2(fi0, 0.5)).r * s0,
            texture(u_ch_y, vec2(fi0, 0.5)).r * s0
        );
        vec2 pb = spin * vec2(
            texture(u_ch_x, vec2(fi1, 0.5)).r * s0,
            texture(u_ch_y, vec2(fi1, 0.5)).r * s0
        );

        for (int s = 0; s < MAX_SYMMETRY; s++) {
            if (s >= sym_count) break;
            float seg_t;
            float d = seg_dist(p_sym[s], pa, pb, seg_t);
            if (d < min_dist) {
                min_dist    = d;
                min_t_curve = (float(i - 1) + seg_t) / float(N - 1);
            }
        }
    }

    float dist_px = min_dist * u_resolution.y;
    float thick   = u_line_thickness * beat_boost;

    float line = smoothstep(thick, thick * 0.25, dist_px);
    float glow  = exp(-dist_px * dist_px / (thick * thick * 10.0))
                  * u_glow_intensity * beat_boost;

    // Tail fade: dim the "old" end of the trace (min_t_curve → 1.0).
    float brightness = 1.0 - min_t_curve * u_tail_fade;

    vec3  color = get_color(min_t_curve) * brightness;
    float alpha = clamp(line + glow * 0.6, 0.0, 1.0);
    fragColor = vec4(color * (line + glow), alpha);
}
"""


@register
class LissajousVisualization(AbstractVisualization):
    """Phase-portrait Lissajous: plots waveform[i] vs waveform[i+delay]."""

    NAME: ClassVar[str] = "lissajous"
    DISPLAY_NAME: ClassVar[str] = "Lissajous (Beta)"
    DESCRIPTION: ClassVar[str] = (
        "Phase-portrait of the audio waveform — X vs delayed-X creates orbital figures"
    )
    CATEGORY: ClassVar[str] = "waveform"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        # ── Curve shape ──────────────────────────────────────────────────────
        "waveform_smoothing": {
            "type": "int", "default": 8, "min": 1, "max": 64,
            "label": "Waveform Smoothing",
            "description": (
                "Box-filter kernel applied to the waveform before plotting. "
                "Low values = raw/noisy, high values = clean orbital curves. "
                "Start here if the figure looks like random writing."
            ),
        },
        "sample_count": {
            "type": "int", "default": 256, "min": 64, "max": 512,
            "label": "Sample Count",
            "description": (
                "Number of waveform samples used to draw the curve. "
                "Higher = smoother trace but heavier on GPU."
            ),
        },
        "delay_samples": {
            "type": "int", "default": 32, "min": 0, "max": 256,
            "label": "Delay",
            "description": (
                "Sample offset between the X and Y channels. "
                "0 = diagonal line, quarter-period of dominant frequency = circle/ellipse."
            ),
        },
        "amplitude_scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Amplitude Scale",
            "description": "Scales the signal amplitude — zooms the figure in/out.",
        },
        # ── Symmetry ─────────────────────────────────────────────────────────
        "symmetry": {
            "type": "int", "default": 1, "min": 1, "max": 8,
            "label": "Symmetry",
            "description": (
                "Rotational copies of the figure. "
                "1 = normal, 2 = two opposing copies, 4 = four-fold, etc. "
                "Higher values make noisy signals look structured."
            ),
        },
        "mirror_x": {
            "type": "bool", "default": False,
            "label": "Mirror X",
            "description": (
                "Fold the left half onto the right before applying symmetry. "
                "Doubles effective symmetry and creates kaleidoscope patterns."
            ),
        },
        # ── Motion ───────────────────────────────────────────────────────────
        "spin_speed": {
            "type": "float", "default": 0.0, "min": -5.0, "max": 5.0,
            "label": "Spin Speed",
            "description": (
                "Auto-rotate the figure over time. "
                "Positive = clockwise, negative = counter-clockwise."
            ),
        },
        # ── Appearance ───────────────────────────────────────────────────────
        "line_thickness": {
            "type": "float", "default": 2.5, "min": 0.5, "max": 20.0,
            "label": "Line Thickness",
            "description": "Thickness of the Lissajous trace in pixels.",
        },
        "glow_intensity": {
            "type": "float", "default": 0.6, "min": 0.0, "max": 3.0,
            "label": "Glow Intensity",
            "description": "Strength of the phosphor-glow around the trace.",
        },
        "tail_fade": {
            "type": "float", "default": 0.4, "min": 0.0, "max": 1.0,
            "label": "Tail Fade",
            "description": (
                "Dim the trailing end of the curve. "
                "0 = uniform brightness, 1 = only the leading edge is bright."
            ),
        },
        "beat_reactive": {
            "type": "bool", "default": True,
            "label": "Beat Reactive",
            "description": "Pulse line thickness and glow on detected beats.",
        },
        # ── Transform ────────────────────────────────────────────────────────
        "offset_x": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Offset X",
            "description": "Horizontal position offset.",
        },
        "offset_y": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Offset Y",
            "description": "Vertical position offset.",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Scale",
            "description": "Viewport zoom. Below 1.0 zooms in, above 1.0 zooms out.",
        },
        "rotation": {
            "type": "float", "default": 0.0, "min": -180.0, "max": 180.0,
            "label": "Rotation",
            "description": "Viewport rotation angle in degrees.",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._ch_x_tex: moderngl.Texture | None = None
        self._ch_y_tex: moderngl.Texture | None = None
        self._tex_size: int = 0

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=_LISSAJOUS_FRAG,
        )

        vertices = np.array([
            -1.0, -1.0,  0.0, 0.0,
             1.0, -1.0,  1.0, 0.0,
            -1.0,  1.0,  0.0, 1.0,
             1.0,  1.0,  1.0, 1.0,
        ], dtype="f4")
        self._vbo = self.ctx.buffer(vertices)
        self._vao = self.ctx.vertex_array(
            self._program,
            [(self._vbo, "2f 2f", "in_position", "in_texcoord")],
        )

        self._create_textures(self.get_param("sample_count", 256))

    def _create_textures(self, n: int) -> None:
        """(Re-)allocate channel textures for n samples."""
        for tex in (self._ch_x_tex, self._ch_y_tex):
            if tex is not None:
                tex.release()
        self._ch_x_tex = self.ctx.texture((n, 1), 1, dtype="f4")
        self._ch_x_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._ch_y_tex = self.ctx.texture((n, 1), 1, dtype="f4")
        self._ch_y_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._tex_size = n

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None:
            return
        if self._ch_x_tex is None or self._ch_y_tex is None:
            return

        sample_count = self.get_param("sample_count", 256)
        delay        = self.get_param("delay_samples", 32)
        smoothing    = max(1, self.get_param("waveform_smoothing", 8))

        if self._tex_size != sample_count:
            self._create_textures(sample_count)

        # Build phase-portrait channels.
        # ch_x[i] = smoothed_waveform[i], ch_y[i] = smoothed_waveform[i + delay].
        total_needed = sample_count + delay
        wf = frame.waveform

        if len(wf) >= total_needed:
            indices  = np.linspace(0, len(wf) - 1, total_needed, dtype=int)
            resampled = wf[indices].astype("f4")
        else:
            resampled = np.resize(wf, total_needed).astype("f4")

        # Box-filter smoothing: convolve then trim the edge smear via 'same' mode.
        if smoothing > 1:
            kernel    = np.ones(smoothing, dtype="f4") / smoothing
            resampled = np.convolve(resampled, kernel, mode="same")

        ch_x = resampled[:sample_count].astype("f4")
        ch_y = resampled[delay: delay + sample_count].astype("f4")

        self._ch_x_tex.write(ch_x.tobytes())
        self._ch_y_tex.write(ch_y.tobytes())

        fbo.use()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

        prog = self._program
        self._ch_x_tex.use(location=0)
        self._ch_y_tex.use(location=1)

        self._set_uniform(prog, "u_ch_x", 0)
        self._set_uniform(prog, "u_ch_y", 1)
        self._set_uniform(prog, "u_sample_count", sample_count)
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_line_thickness", self.get_param("line_thickness", 2.5))
        self._set_uniform(prog, "u_glow_intensity", self.get_param("glow_intensity", 0.6))
        self._set_uniform(prog, "u_amplitude_scale", self.get_param("amplitude_scale", 1.0))
        self._set_uniform(prog, "u_amplitude", frame.amplitude)
        self._set_uniform(prog, "u_tail_fade", self.get_param("tail_fade", 0.4))
        self._set_uniform(prog, "u_spin_speed", self.get_param("spin_speed", 0.0))
        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_symmetry", self.get_param("symmetry", 1))
        self._set_uniform(prog, "u_mirror_x", self.get_param("mirror_x", False))

        beat_intensity = frame.beat_intensity if self.get_param("beat_reactive", True) else 0.0
        self._set_uniform(prog, "u_beat_intensity", beat_intensity)

        self._set_uniform(
            prog, "u_offset",
            (self.get_param("offset_x", 0.0), self.get_param("offset_y", 0.0)),
        )
        self._set_uniform(prog, "u_scale", self.get_param("scale", 1.0))
        self._set_uniform(prog, "u_rotation", math.radians(self.get_param("rotation", 0.0)))

        colors = self.params.params.get("_colors", [(0.0, 0.9, 1.0), (1.0, 0.0, 0.8)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        self._vao.render(moderngl.TRIANGLE_STRIP)
        self.ctx.disable(moderngl.BLEND)

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._ch_x_tex:
            self._ch_x_tex.release()
        if self._ch_y_tex:
            self._ch_y_tex.release()
        if self._program:
            self._program.release()

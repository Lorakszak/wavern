"""Tunnel visualization — concentric rings pulsing inward/outward, driven by audio."""

import math
from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

TUNNEL_FRAG = """
#version 330 core

uniform float u_time;
uniform float u_offset;
uniform float u_amplitude;
uniform float u_bass;
uniform float u_sub_bass;
uniform float u_mid;
uniform float u_beat_burst;
uniform vec3  u_colors[8];
uniform int   u_color_count;
uniform vec2  u_resolution;
uniform int   u_ring_count;
uniform int   u_direction;    // 0 = inward, 1 = outward
uniform float u_ring_thickness;
uniform float u_ring_gap;
uniform float u_spiral_twist;
uniform float u_perspective;
uniform float u_depth_fade;
uniform float u_color_cycle_speed;
uniform float u_color_spread;
uniform float u_glow_intensity;
uniform float u_pulse_intensity;
uniform int   u_ring_shape;   // 0=circle, 1=square, 2=hexagon, 3=octagon
uniform vec2  u_position;
uniform float u_scale;
uniform float u_rotation;

in vec2 v_texcoord;
out vec4 fragColor;

#define PI  3.14159265359
#define TAU 6.28318530718

vec3 get_color(float t) {
    t = fract(t);
    if (u_color_count <= 1) return u_colors[0];
    float idx_f = t * float(u_color_count - 1);
    int idx = int(floor(idx_f));
    float fract_t = idx_f - float(idx);
    idx = clamp(idx, 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], fract_t);
}

// Shape distance: always positive distance from origin
float dist_circle(vec2 p)  { return length(p); }
float dist_square(vec2 p)  { vec2 a = abs(p); return max(a.x, a.y); }
float dist_hexagon(vec2 p) { p = abs(p); return max(dot(p, vec2(0.866025, 0.5)), p.y); }
float dist_octagon(vec2 p) {
    p = abs(p);
    return max(max(dot(p, vec2(0.9238795, 0.3826834)),
                   dot(p, vec2(0.3826834, 0.9238795))),
               max(p.x, p.y));
}

float shape_dist(vec2 p) {
    if (u_ring_shape == 1) return dist_square(p);
    if (u_ring_shape == 2) return dist_hexagon(p);
    if (u_ring_shape == 3) return dist_octagon(p);
    return dist_circle(p);
}

void main() {
    vec2 uv = v_texcoord;
    float aspect = u_resolution.x / u_resolution.y;

    // Inverse of rotate -> scale -> translate
    uv -= u_position;
    uv /= max(u_scale, 0.001);
    uv.x *= aspect;

    // Static rotation
    float c = cos(u_rotation);
    float s = sin(u_rotation);
    uv = mat2(c, s, -s, c) * uv;

    // Distance from tunnel center
    float dist = shape_dist(uv);

    // Polar angle (for spiral twist)
    float angle = atan(uv.y, uv.x);

    // Perspective foreshortening via power curve:
    // exponent > 1 compresses rings near center (far end) and spreads outer rings
    float persp_exp = 1.0 + u_perspective * 3.0;
    float ring_space = pow(clamp(dist, 0.0, 2.0), persp_exp);

    // Spiral twist: offset ring position by polar angle, creating Archimedean spiral
    // At twist=1.0, one full rotation shifts by one ring width
    // Round to integer so that the atan() discontinuity at angle=±PI is absorbed
    // by fract() — a non-integer twist would leave a visible seam along -X axis
    float twist = round(u_spiral_twist);
    float spiral_offset = (angle / TAU) * twist / float(u_ring_count);
    ring_space += spiral_offset;

    // Animated scroll (inward = rings expand outward past you)
    float scroll = u_offset;
    if (u_direction == 1) scroll = -scroll;
    float ring_pos = fract((ring_space - scroll) * float(u_ring_count));

    // Ring mask — ring_pos is 0–1 within each period, center at 0.5
    // ring_thickness is directly the fraction filled (0.3 = 30% of period)
    float pulse = 1.0 + u_pulse_intensity * u_amplitude * 0.5;
    float half_thick = u_ring_thickness * pulse * 0.5;
    float dist_to_mid = abs(ring_pos - 0.5);

    // Smooth edges
    float softness = max(half_thick * 0.15, 0.005);
    float ring_mask = smoothstep(half_thick, half_thick - softness, dist_to_mid);

    // Glow around ring edges
    float glow_width = half_thick * 1.5 + 0.02;
    float glow = exp(-dist_to_mid * dist_to_mid / (glow_width * glow_width))
                 * u_glow_intensity * (1.0 + u_amplitude * 0.5 + u_beat_burst * 0.3);

    // Depth fade: bell-curve — bright in middle distance, dim at center + edges
    float depth_t = clamp(dist / 1.0, 0.0, 1.0);
    float depth_bell = smoothstep(0.0, 0.25, depth_t) * (1.0 - smoothstep(0.6, 1.0, depth_t));
    float depth_alpha = mix(1.0, depth_bell, u_depth_fade);
    // Fade the very center point
    float center_mask = smoothstep(0.0, 0.03, dist);

    // Color: cycle along normalised depth + time
    float norm_dist = clamp(dist / 1.0, 0.0, 1.0);
    float depth_idx = fract(norm_dist * u_color_spread - u_time * u_color_cycle_speed * 0.1);
    depth_idx = fract(depth_idx + u_mid * 0.1);
    vec3 color = get_color(depth_idx);

    // Bright glow at tunnel center ("light at end of tunnel")
    color *= 1.0 + smoothstep(0.15, 0.0, dist) * 1.5;

    float alpha = (ring_mask + glow) * depth_alpha * center_mask;
    alpha = clamp(alpha, 0.0, 1.0);

    fragColor = vec4(color * alpha, alpha);
}
"""


@register
class TunnelVisualization(AbstractVisualization):
    """Concentric rings creating a tunnel zoom effect driven by audio."""

    NAME: ClassVar[str] = "tunnel"
    DISPLAY_NAME: ClassVar[str] = "Tunnel (Alpha)"
    DESCRIPTION: ClassVar[str] = "Concentric rings creating a tunnel zoom effect driven by audio"
    CATEGORY: ClassVar[str] = "abstract"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "ring_count": {
            "type": "int", "default": 20, "min": 4, "max": 64,
            "label": "Ring Count",
            "description": "Number of visible concentric rings.",
        },
        "direction": {
            "type": "choice", "default": "inward", "choices": ["inward", "outward"],
            "label": "Direction",
            "description": "'inward' = flying into tunnel, 'outward' = rings expanding toward you.",
        },
        "base_speed": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 10.0,
            "label": "Base Speed",
            "description": "Baseline tunnel zoom speed.",
        },
        "bass_drive": {
            "type": "float", "default": 0.8, "min": 0.0, "max": 3.0,
            "label": "Bass Drive",
            "description": "How much bass energy accelerates ring movement.",
        },
        "beat_burst": {
            "type": "float", "default": 1.5, "min": 0.0, "max": 5.0,
            "label": "Beat Burst",
            "description": "Acceleration burst on beat detection.",
        },
        "ring_thickness": {
            "type": "float", "default": 0.3, "min": 0.05, "max": 1.0,
            "label": "Ring Thickness",
            "description": "Thickness of each ring (0.05=thin lines, 1.0=fills gap).",
        },
        "ring_gap": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 1.0,
            "label": "Ring Gap",
            "description": "Spacing between rings.",
        },
        "spiral_twist": {
            "type": "int", "default": 0, "min": -10, "max": 10,
            "label": "Spiral Twist",
            "description": "Number of spiral arms (0 = no twist, positive = CW, negative = CCW).",
        },
        "perspective": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 1.0,
            "label": "Perspective",
            "description": "Depth perspective strength (0 = flat, 1 = strong perspective shrink).",
        },
        "depth_fade": {
            "type": "float", "default": 0.7, "min": 0.0, "max": 1.0,
            "label": "Depth Fade",
            "description": "How much rings fade with depth (0 = no fade, 1 = full fade).",
        },
        "color_cycle_speed": {
            "type": "float", "default": 1.0, "min": 0.0, "max": 5.0,
            "label": "Color Cycle Speed",
            "description": "Speed of color cycling along ring depth.",
        },
        "color_spread": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 5.0,
            "label": "Color Spread",
            "description": "How many times the palette repeats across ring depth.",
        },
        "glow_intensity": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 2.0,
            "label": "Glow Intensity",
            "description": "Glow/bloom around ring edges.",
        },
        "pulse_intensity": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 2.0,
            "label": "Pulse Intensity",
            "description": "How much rings pulse in thickness with amplitude.",
        },
        "ring_shape": {
            "type": "choice", "default": "circle", "choices": ["circle", "square", "hexagon", "octagon"],
            "label": "Ring Shape",
            "description": "Shape of the concentric rings.",
        },
        "position_x": {
            "type": "float", "default": 0.5, "min": -0.25, "max": 1.25,
            "label": "Position X",
            "description": "Horizontal position (0.0 = left edge, 1.0 = right edge).",
        },
        "position_y": {
            "type": "float", "default": 0.5, "min": -0.25, "max": 1.25,
            "label": "Position Y",
            "description": "Vertical position (0.0 = bottom edge, 1.0 = top edge).",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Scale",
            "description": "Overall zoom.",
        },
        "rotation": {
            "type": "float", "default": 0.0, "min": -180.0, "max": 180.0,
            "label": "Rotation",
            "description": "Static rotation angle in degrees.",
        },
    }

    _SHAPE_MAP: ClassVar[dict[str, int]] = {
        "circle": 0,
        "square": 1,
        "hexagon": 2,
        "octagon": 3,
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._accumulated_offset: float = 0.0
        self._beat_burst_energy: float = 0.0
        self._prev_time: float = 0.0

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=TUNNEL_FRAG,
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

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None:
            return

        # Compute dt
        dt = frame.timestamp - self._prev_time
        if dt < 0.0 or dt > 0.5:
            dt = 1.0 / 60.0
        self._prev_time = frame.timestamp

        # Audio values
        bass = frame.frequency_bands_norm.get("bass", 0.0)
        sub_bass = frame.frequency_bands_norm.get("sub_bass", 0.0)
        mid = frame.frequency_bands_norm.get("mid", 0.0)

        # Beat burst: inject energy on beat, then decay
        if frame.beat:
            self._beat_burst_energy = min(
                self._beat_burst_energy + frame.beat_intensity * self.get_param("beat_burst", 1.5),
                self.get_param("beat_burst", 1.5) * 2.0,
            )
        decay = math.exp(-dt * 4.0)
        self._beat_burst_energy *= decay

        # Speed = base + bass-driven + burst
        base_speed = self.get_param("base_speed", 1.0)
        bass_drive = self.get_param("bass_drive", 0.8)
        effective_speed = base_speed + (bass + sub_bass * 0.5) * bass_drive + self._beat_burst_energy
        self._accumulated_offset += effective_speed * dt * 0.5

        # Wrap offset to avoid float precision loss over long sessions
        self._accumulated_offset = math.fmod(self._accumulated_offset, 1000.0)

        fbo.use()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

        prog = self._program

        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_offset", self._accumulated_offset)
        self._set_uniform(prog, "u_amplitude", frame.amplitude_envelope)
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_sub_bass", sub_bass)
        self._set_uniform(prog, "u_mid", mid)
        self._set_uniform(prog, "u_beat_burst", self._beat_burst_energy)
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_ring_count", self.get_param("ring_count", 20))
        self._set_uniform(prog, "u_direction", 0 if self.get_param("direction", "inward") == "inward" else 1)
        self._set_uniform(prog, "u_ring_thickness", self.get_param("ring_thickness", 0.3))
        self._set_uniform(prog, "u_ring_gap", self.get_param("ring_gap", 0.5))
        self._set_uniform(prog, "u_spiral_twist", self.get_param("spiral_twist", 0.0))
        self._set_uniform(prog, "u_perspective", self.get_param("perspective", 0.5))
        self._set_uniform(prog, "u_depth_fade", self.get_param("depth_fade", 0.7))
        self._set_uniform(prog, "u_color_cycle_speed", self.get_param("color_cycle_speed", 1.0))
        self._set_uniform(prog, "u_color_spread", self.get_param("color_spread", 1.0))
        self._set_uniform(prog, "u_glow_intensity", self.get_param("glow_intensity", 0.5))
        self._set_uniform(prog, "u_pulse_intensity", self.get_param("pulse_intensity", 0.5))
        self._set_uniform(
            prog, "u_ring_shape",
            self._SHAPE_MAP.get(self.get_param("ring_shape", "circle"), 0),
        )
        self._set_uniform(prog, "u_position", (self.get_param("position_x", 0.5), self.get_param("position_y", 0.5)))
        self._set_uniform(prog, "u_scale", self.get_param("scale", 1.0))
        self._set_uniform(prog, "u_rotation", math.radians(self.get_param("rotation", 0.0)))

        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67), (1.0, 0.0, 0.67)])
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
        if self._program:
            self._program.release()

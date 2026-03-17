"""CRT Oscilloscope visualization — retro phosphor display with barrel distortion and scanlines."""

from typing import Any, ClassVar

import math

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register


OSCILLOSCOPE_FRAG = """
#version 330 core

uniform sampler2D u_waveform_tex;
uniform int u_sample_count;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec3 u_color;

uniform int u_display_mode;        // 0=line, 1=dot, 2=filled
uniform float u_line_thickness;
uniform float u_wave_range;
uniform float u_phosphor_glow;
uniform float u_glow_radius;

uniform float u_barrel_distortion;
uniform float u_scanline_intensity;
uniform int u_scanline_count;
uniform float u_chromatic_aberration;
uniform float u_vignette;
uniform float u_noise_intensity;
uniform float u_screen_flicker;
uniform float u_screen_tint;

uniform int u_graticule_enabled;
uniform float u_graticule_intensity;
uniform int u_graticule_divisions;
uniform int u_bezel;
uniform int u_fill_screen;

uniform vec2 u_offset;
uniform float u_scale;
uniform float u_rotation;

in vec2 v_texcoord;
out vec4 fragColor;

#define PI 3.14159265359

float hash21(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 19.19);
    return fract(p.x * p.y);
}

vec2 barrel_distort(vec2 uv, float k) {
    vec2 c = uv * 2.0 - 1.0;
    float r2 = dot(c, c);
    c *= 1.0 + k * r2;
    return c * 0.5 + 0.5;
}

float sample_wave(float x) {
    return texture(u_waveform_tex, vec2(clamp(x, 0.001, 0.999), 0.5)).r;
}

void main() {
    vec2 uv = v_texcoord;

    // Transform
    uv -= 0.5;
    uv -= u_offset;
    uv /= max(u_scale, 0.001);
    float cr = cos(u_rotation), sr = sin(u_rotation);
    uv = mat2(cr, sr, -sr, cr) * uv;
    uv += 0.5;

    // Bezel and barrel distortion (skipped in fill_screen mode)
    vec2 cuv;
    if (u_fill_screen != 0) {
        cuv = uv;
    } else {
        if (u_bezel != 0) {
            vec2 q = abs(uv * 2.0 - 1.0) - vec2(0.9, 0.88);
            float r = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
            if (r > 0.06) { fragColor = vec4(0.0); return; }
        }
        cuv = barrel_distort(uv, u_barrel_distortion);
        if (cuv.x < 0.0 || cuv.x > 1.0 || cuv.y < 0.0 || cuv.y > 1.0) {
            fragColor = vec4(0.0);
            return;
        }
    }

    float py = 1.0 / u_resolution.y;
    float px = 1.0 / u_resolution.x;
    float thickness = u_line_thickness * py;

    // Phosphor background tint
    vec3 screen = u_color * u_screen_tint * 0.3;

    // Graticule grid
    if (u_graticule_enabled != 0) {
        float d = float(u_graticule_divisions);
        vec2 gf = fract(cuv * d);
        float gx = smoothstep(2.0 * px, 0.0, min(gf.x, 1.0 - gf.x));
        float gy = smoothstep(2.0 * py, 0.0, min(gf.y, 1.0 - gf.y));
        float grid = max(gx, gy) * u_graticule_intensity;
        // Center axis brighter
        float ax = smoothstep(3.0 * px, 0.0, abs(cuv.x - 0.5)) * u_graticule_intensity * 1.5;
        float ay = smoothstep(3.0 * py, 0.0, abs(cuv.y - 0.5)) * u_graticule_intensity * 1.5;
        screen += u_color * (grid + max(ax, ay));
    }

    // Chromatic aberration offset
    float ca = u_chromatic_aberration * 0.003;

    // Sample waveform for each RGB channel (offset horizontally)
    float wave_y  = sample_wave(cuv.x)      * u_wave_range + 0.5;
    float wave_yr = sample_wave(cuv.x + ca) * u_wave_range + 0.5;
    float wave_yb = sample_wave(cuv.x - ca) * u_wave_range + 0.5;

    float dy  = abs(cuv.y - wave_y);
    float dyr = abs(cuv.y - wave_yr);
    float dyb = abs(cuv.y - wave_yb);

    float tr, tg, tb;
    if (u_display_mode == 1) {
        // Dot mode — render discrete sample points
        float step_x = 1.0 / float(u_sample_count);
        float nx = round(cuv.x / step_x) * step_x;
        float ny = sample_wave(nx) * u_wave_range + 0.5;
        float dot_size = u_line_thickness * 1.5;
        float dot_d = length(vec2((cuv.x - nx) / px, (cuv.y - ny) / py));
        tr = tg = tb = smoothstep(dot_size, dot_size * 0.3, dot_d);
    } else if (u_display_mode == 2) {
        // Filled mode — fill area between trace and center
        float mid = 0.5;
        float fill_g = 0.0, fill_r = 0.0, fill_b = 0.0;
        if ((cuv.y >= mid && cuv.y <= wave_y)  || (cuv.y <= mid && cuv.y >= wave_y))  fill_g = 0.6;
        if ((cuv.y >= mid && cuv.y <= wave_yr) || (cuv.y <= mid && cuv.y >= wave_yr)) fill_r = 0.6;
        if ((cuv.y >= mid && cuv.y <= wave_yb) || (cuv.y <= mid && cuv.y >= wave_yb)) fill_b = 0.6;
        float line_g = smoothstep(thickness, thickness * 0.2, dy);
        float line_r = smoothstep(thickness, thickness * 0.2, dyr);
        float line_b = smoothstep(thickness, thickness * 0.2, dyb);
        tr = clamp(fill_r + line_r, 0.0, 1.0);
        tg = clamp(fill_g + line_g, 0.0, 1.0);
        tb = clamp(fill_b + line_b, 0.0, 1.0);
    } else {
        // Line mode (default)
        tr = smoothstep(thickness, thickness * 0.2, dyr);
        tg = smoothstep(thickness, thickness * 0.2, dy);
        tb = smoothstep(thickness, thickness * 0.2, dyb);
    }

    // Phosphor glow — gaussian falloff from trace centre (green channel distance)
    float glow_sigma = u_glow_radius * py * 10.0;
    float glow = exp(-dy * dy / (glow_sigma * glow_sigma + 1e-6)) * u_phosphor_glow * 0.6;

    screen += vec3(tr, tg, tb) * u_color + u_color * glow;

    // Scanlines
    float sl = sin(cuv.y * float(u_scanline_count) * PI);
    screen *= 1.0 - u_scanline_intensity * (1.0 - sl * sl * 0.85);

    // Vignette
    vec2 vc = cuv * 2.0 - 1.0;
    screen *= max(0.0, 1.0 - dot(vc, vc) * u_vignette);

    // Noise (quantised time for static look)
    float noise = hash21(cuv + vec2(floor(u_time * 30.0) * 0.13)) * u_noise_intensity;
    screen += vec3(noise) * mix(vec3(1.0), u_color, 0.4);

    // Flicker (frame-level brightness jitter)
    float flicker = 1.0 - u_screen_flicker * hash21(vec2(floor(u_time * 60.0), 0.5));
    screen *= flicker;

    // Edge soft fade at screen boundary (suppressed in fill_screen mode)
    float edge = (u_fill_screen != 0)
        ? 1.0
        : 1.0 - smoothstep(0.92, 1.0, max(abs(vc.x), abs(vc.y)));
    screen *= edge;

    fragColor = vec4(clamp(screen, 0.0, 1.0), edge);
}
"""


PERSISTENCE_BLEND_FRAG = """
#version 330 core

uniform sampler2D u_current_tex;
uniform sampler2D u_persist_tex;
uniform float u_decay;

in vec2 v_texcoord;
out vec4 fragColor;

void main() {
    vec4 cur  = texture(u_current_tex, v_texcoord);
    vec4 prev = texture(u_persist_tex, v_texcoord);
    fragColor = max(cur, prev * u_decay);
}
"""


@register
class OscilloscopeVisualization(AbstractVisualization):
    """Retro CRT oscilloscope with phosphor glow, barrel distortion, and scanlines."""

    NAME: ClassVar[str] = "oscilloscope"
    DISPLAY_NAME: ClassVar[str] = "CRT Oscilloscope (Beta)"
    DESCRIPTION: ClassVar[str] = (
        "Retro CRT oscilloscope with phosphor glow, barrel distortion, scanlines, "
        "chromatic aberration, and optional graticule grid"
    )
    CATEGORY: ClassVar[str] = "waveform"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        # Trace
        "display_mode": {
            "type": "str", "default": "line", "options": ["line", "dot", "filled"],
            "label": "Display Mode",
            "description": "How the trace is drawn: line, individual dots, or filled area.",
        },
        "line_thickness": {
            "type": "float", "default": 2.5, "min": 0.5, "max": 20.0,
            "label": "Line Thickness",
            "description": "Trace width in pixels.",
        },
        "sample_count": {
            "type": "int", "default": 512, "min": 64, "max": 2048,
            "label": "Sample Count",
            "description": "Waveform sample resolution. Higher = more detail.",
        },
        "amplitude_scale": {
            "type": "float", "default": 1.5, "min": 0.1, "max": 10.0,
            "label": "Amplitude Scale",
            "description": "Vertical amplitude multiplier.",
        },
        "wave_range": {
            "type": "float", "default": 0.35, "min": 0.05, "max": 0.5,
            "label": "Wave Range",
            "description": "Vertical extent of waveform (fraction of screen height).",
        },
        "trigger_mode": {
            "type": "str", "default": "rising", "options": ["none", "rising", "falling"],
            "label": "Trigger Mode",
            "description": "Edge trigger for stable display. 'none' = free-running.",
        },
        # Phosphor
        "phosphor_glow": {
            "type": "float", "default": 1.0, "min": 0.0, "max": 3.0,
            "label": "Phosphor Glow",
            "description": "Phosphor bloom intensity.",
        },
        "glow_radius": {
            "type": "float", "default": 1.5, "min": 0.5, "max": 5.0,
            "label": "Glow Radius",
            "description": "Glow spread radius.",
        },
        "phosphor_persistence": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 0.95,
            "label": "Phosphor Persistence",
            "description": "Afterglow trail decay factor (0 = off, higher = longer trail).",
        },
        # CRT Effects
        "barrel_distortion": {
            "type": "float", "default": 0.15, "min": 0.0, "max": 0.5,
            "label": "Barrel Distortion",
            "description": "Screen curvature amount.",
        },
        "scanline_intensity": {
            "type": "float", "default": 0.3, "min": 0.0, "max": 1.0,
            "label": "Scanline Intensity",
            "description": "Horizontal scanline visibility.",
        },
        "scanline_count": {
            "type": "int", "default": 400, "min": 50, "max": 1200,
            "label": "Scanline Count",
            "description": "Number of horizontal scanlines.",
        },
        "chromatic_aberration": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 3.0,
            "label": "Chromatic Aberration",
            "description": "RGB channel separation amount.",
        },
        "vignette": {
            "type": "float", "default": 0.4, "min": 0.0, "max": 1.5,
            "label": "Vignette",
            "description": "Edge darkening strength.",
        },
        "noise_intensity": {
            "type": "float", "default": 0.03, "min": 0.0, "max": 0.2,
            "label": "Noise Intensity",
            "description": "CRT static noise amount.",
        },
        # Screen
        "screen_flicker": {
            "type": "float", "default": 0.02, "min": 0.0, "max": 0.15,
            "label": "Screen Flicker",
            "description": "Brightness instability (subtle CRT flicker).",
        },
        "screen_tint": {
            "type": "float", "default": 0.05, "min": 0.0, "max": 0.2,
            "label": "Screen Tint",
            "description": "Faint phosphor background color intensity.",
        },
        "graticule_enabled": {
            "type": "bool", "default": True,
            "label": "Graticule",
            "description": "Show measurement grid overlay.",
        },
        "graticule_intensity": {
            "type": "float", "default": 0.15, "min": 0.0, "max": 0.5,
            "label": "Graticule Intensity",
            "description": "Grid line brightness.",
        },
        "graticule_divisions": {
            "type": "int", "default": 10, "min": 4, "max": 20,
            "label": "Graticule Divisions",
            "description": "Number of grid divisions.",
        },
        "bezel": {
            "type": "bool", "default": False,
            "label": "Bezel",
            "description": "Show rounded CRT bezel frame.",
        },
        "fill_screen": {
            "type": "bool", "default": False,
            "label": "Fill Screen",
            "description": "Stretch trace to fill the entire canvas, bypassing CRT frame and barrel distortion.",
        },
        # Transform
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
            "description": "Zoom level.",
        },
        "rotation": {
            "type": "float", "default": 0.0, "min": -180.0, "max": 180.0,
            "label": "Rotation",
            "description": "Rotation angle in degrees.",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._blend_program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._blend_vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._waveform_tex: moderngl.Texture | None = None
        # Persistence ping-pong FBOs (created lazily on first use)
        self._osc_fbo: moderngl.Framebuffer | None = None
        self._osc_tex: moderngl.Texture | None = None
        self._ping_fbo: moderngl.Framebuffer | None = None
        self._ping_tex: moderngl.Texture | None = None
        self._pong_fbo: moderngl.Framebuffer | None = None
        self._pong_tex: moderngl.Texture | None = None
        self._fbo_resolution: tuple[int, int] | None = None
        self._ping_is_front: bool = True

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=OSCILLOSCOPE_FRAG,
        )
        self._blend_program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=PERSISTENCE_BLEND_FRAG,
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
        self._blend_vao = self.ctx.vertex_array(
            self._blend_program,
            [(self._vbo, "2f 2f", "in_position", "in_texcoord")],
        )

        sample_count = self.get_param("sample_count", 512)
        self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
        self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def _ensure_persistence_fbos(self, resolution: tuple[int, int]) -> None:
        if self._fbo_resolution == resolution:
            return
        self._release_persistence_fbos()
        w, h = resolution
        self._osc_tex = self.ctx.texture((w, h), 4)
        self._osc_fbo = self.ctx.framebuffer(color_attachments=[self._osc_tex])
        self._ping_tex = self.ctx.texture((w, h), 4)
        self._ping_fbo = self.ctx.framebuffer(color_attachments=[self._ping_tex])
        self._pong_tex = self.ctx.texture((w, h), 4)
        self._pong_fbo = self.ctx.framebuffer(color_attachments=[self._pong_tex])
        for fbo_obj in (self._osc_fbo, self._ping_fbo, self._pong_fbo):
            fbo_obj.use()
            fbo_obj.clear(0.0, 0.0, 0.0, 0.0)
        self._fbo_resolution = resolution
        self._ping_is_front = True

    def _release_persistence_fbos(self) -> None:
        for attr in (
            "_osc_fbo", "_osc_tex",
            "_ping_fbo", "_ping_tex",
            "_pong_fbo", "_pong_tex",
        ):
            obj = getattr(self, attr, None)
            if obj is not None:
                obj.release()
                setattr(self, attr, None)
        self._fbo_resolution = None

    def _upload_waveform(self, frame: FrameAnalysis) -> int:
        """Resample, trigger-align, and upload waveform to texture.

        Returns:
            The sample_count actually used.
        """
        sample_count = self.get_param("sample_count", 512)
        amp_scale = self.get_param("amplitude_scale", 1.5)
        trigger_mode = self.get_param("trigger_mode", "rising")

        waveform = frame.waveform
        offset = self._find_trigger_offset(waveform, trigger_mode)
        waveform = np.roll(waveform, -offset)

        if len(waveform) > sample_count:
            indices = np.linspace(0, len(waveform) - 1, sample_count, dtype=int)
            waveform = waveform[indices]
        elif len(waveform) < sample_count:
            waveform = np.pad(waveform, (0, sample_count - len(waveform)))

        waveform = (waveform * amp_scale).astype("f4")

        if self._waveform_tex is not None and self._waveform_tex.size != (sample_count, 1):
            self._waveform_tex.release()
            self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
            self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        if self._waveform_tex is not None:
            self._waveform_tex.write(waveform[:sample_count].tobytes())
            self._waveform_tex.use(location=0)

        return sample_count

    def _set_oscilloscope_uniforms(
        self,
        prog: moderngl.Program,
        frame: FrameAnalysis,
        resolution: tuple[int, int],
        sample_count: int,
    ) -> None:
        display_mode_map = {"line": 0, "dot": 1, "filled": 2}
        display_mode = display_mode_map.get(self.get_param("display_mode", "line"), 0)

        color = self.params.params.get("_primary_color", (0.2, 1.0, 0.4))

        self._set_uniform(prog, "u_waveform_tex", 0)
        self._set_uniform(prog, "u_sample_count", sample_count)
        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_color", color)
        self._set_uniform(prog, "u_display_mode", display_mode)
        self._set_uniform(prog, "u_line_thickness", self.get_param("line_thickness", 2.5))
        self._set_uniform(prog, "u_wave_range", self.get_param("wave_range", 0.35))
        self._set_uniform(prog, "u_phosphor_glow", self.get_param("phosphor_glow", 1.0))
        self._set_uniform(prog, "u_glow_radius", self.get_param("glow_radius", 1.5))
        self._set_uniform(prog, "u_barrel_distortion", self.get_param("barrel_distortion", 0.15))
        self._set_uniform(prog, "u_scanline_intensity", self.get_param("scanline_intensity", 0.3))
        self._set_uniform(prog, "u_scanline_count", self.get_param("scanline_count", 400))
        self._set_uniform(prog, "u_chromatic_aberration", self.get_param("chromatic_aberration", 0.5))
        self._set_uniform(prog, "u_vignette", self.get_param("vignette", 0.4))
        self._set_uniform(prog, "u_noise_intensity", self.get_param("noise_intensity", 0.03))
        self._set_uniform(prog, "u_screen_flicker", self.get_param("screen_flicker", 0.02))
        self._set_uniform(prog, "u_screen_tint", self.get_param("screen_tint", 0.05))
        self._set_uniform(prog, "u_graticule_enabled", 1 if self.get_param("graticule_enabled", True) else 0)
        self._set_uniform(prog, "u_graticule_intensity", self.get_param("graticule_intensity", 0.15))
        self._set_uniform(prog, "u_graticule_divisions", self.get_param("graticule_divisions", 10))
        self._set_uniform(prog, "u_bezel", 1 if self.get_param("bezel", False) else 0)
        self._set_uniform(prog, "u_fill_screen", 1 if self.get_param("fill_screen", False) else 0)
        self._set_uniform(prog, "u_offset", (self.get_param("offset_x", 0.0), self.get_param("offset_y", 0.0)))
        self._set_uniform(prog, "u_scale", self.get_param("scale", 1.0))
        self._set_uniform(prog, "u_rotation", math.radians(self.get_param("rotation", 0.0)))

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None or self._waveform_tex is None:
            return

        sample_count = self._upload_waveform(frame)
        persistence = self.get_param("phosphor_persistence", 0.0)

        if persistence > 0.0:
            self._ensure_persistence_fbos(resolution)
            assert (
                self._osc_fbo is not None
                and self._osc_tex is not None
                and self._blend_program is not None
                and self._blend_vao is not None
                and self._ping_fbo is not None
                and self._ping_tex is not None
                and self._pong_fbo is not None
                and self._pong_tex is not None
            )

            # Step 1: render oscilloscope to internal FBO
            self._osc_fbo.use()
            self._osc_fbo.clear(0.0, 0.0, 0.0, 0.0)
            self._set_oscilloscope_uniforms(self._program, frame, resolution, sample_count)
            self._vao.render(moderngl.TRIANGLE_STRIP)

            # Step 2: blend osc + previous accumulation → front FBO (ping-pong)
            front_fbo = self._ping_fbo if self._ping_is_front else self._pong_fbo
            front_tex = self._ping_tex if self._ping_is_front else self._pong_tex
            back_tex = self._pong_tex if self._ping_is_front else self._ping_tex

            front_fbo.use()
            self._osc_tex.use(location=0)
            back_tex.use(location=1)
            bprog = self._blend_program
            self._set_uniform(bprog, "u_current_tex", 0)
            self._set_uniform(bprog, "u_persist_tex", 1)
            self._set_uniform(bprog, "u_decay", persistence)
            self._blend_vao.render(moderngl.TRIANGLE_STRIP)

            # Step 3: copy accumulated result to external FBO
            fbo.use()
            front_tex.use(location=0)
            self._osc_tex.use(location=1)  # dummy; decay=0 makes it irrelevant
            self._set_uniform(bprog, "u_current_tex", 0)
            self._set_uniform(bprog, "u_persist_tex", 1)
            self._set_uniform(bprog, "u_decay", 0.0)
            self._blend_vao.render(moderngl.TRIANGLE_STRIP)

            self._ping_is_front = not self._ping_is_front
        else:
            fbo.use()
            self._set_oscilloscope_uniforms(self._program, frame, resolution, sample_count)
            self._vao.render(moderngl.TRIANGLE_STRIP)

    @staticmethod
    def _find_trigger_offset(waveform: np.ndarray, mode: str) -> int:
        """Find sample index of first edge crossing for stable trigger display.

        Args:
            waveform: Raw audio samples array.
            mode: "rising", "falling", or "none".

        Returns:
            Sample index to start display from (0 if no crossing found or mode is "none").
        """
        if mode == "none" or len(waveform) < 2:
            return 0

        threshold = 0.0
        search_len = len(waveform) // 2  # search first half to preserve display window
        for i in range(search_len):
            if mode == "rising" and waveform[i] <= threshold < waveform[i + 1]:
                return i
            if mode == "falling" and waveform[i] >= threshold > waveform[i + 1]:
                return i
        return 0

    def cleanup(self) -> None:
        self._release_persistence_fbos()
        if self._vao:
            self._vao.release()
        if self._blend_vao:
            self._blend_vao.release()
        if self._vbo:
            self._vbo.release()
        if self._waveform_tex:
            self._waveform_tex.release()
        if self._program:
            self._program.release()
        if self._blend_program:
            self._blend_program.release()

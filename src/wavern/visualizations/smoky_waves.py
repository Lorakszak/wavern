"""Smoky waves visualization — fluid-like wave patterns driven by audio."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

# Inline shader since smoky waves uses a unique procedural approach
SMOKY_WAVES_FRAG = """
#version 330 core

uniform float u_time;
uniform float u_amplitude;
uniform float u_bass;
uniform float u_mid;
uniform float u_treble;
uniform vec3 u_colors[8];
uniform int u_color_count;
uniform vec2 u_resolution;
uniform float u_wave_count;
uniform float u_speed;
uniform float u_turbulence;
uniform float u_thickness;

in vec2 v_texcoord;
out vec4 fragColor;

#define PI 3.14159265359

vec3 get_color(float t) {
    if (u_color_count <= 1) return u_colors[0];
    float idx_f = t * float(u_color_count - 1);
    int idx = int(floor(idx_f));
    float fract_t = idx_f - float(idx);
    idx = clamp(idx, 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], fract_t);
}

float wave(float x, float freq, float phase, float amp) {
    return sin(x * freq + phase) * amp;
}

void main() {
    vec2 uv = v_texcoord;
    float aspect = u_resolution.x / u_resolution.y;

    vec4 final_color = vec4(0.0);
    int waves = int(u_wave_count);

    for (int i = 0; i < waves; i++) {
        float fi = float(i) / float(waves);

        float freq = 2.0 + fi * 4.0;
        float phase = u_time * u_speed * (0.5 + fi * 0.5);
        float base_amp = 0.15 * (1.0 - fi * 0.3);

        // Audio-reactive amplitude
        float audio_amp = u_amplitude * 0.5;
        if (fi < 0.33) audio_amp += u_bass * 0.3;
        else if (fi < 0.66) audio_amp += u_mid * 0.3;
        else audio_amp += u_treble * 0.3;

        float w = wave(uv.x * aspect, freq, phase, base_amp * (1.0 + audio_amp));

        // Add turbulence
        w += wave(uv.x * aspect, freq * 2.3, phase * 1.7, base_amp * u_turbulence * 0.3);
        w += wave(uv.x * aspect, freq * 4.1, phase * 0.8, base_amp * u_turbulence * 0.15);

        float center_y = 0.5 + fi * 0.06 - float(waves) * 0.03;
        float dist = abs(uv.y - center_y - w);

        float thickness = u_thickness * 0.02 * (1.0 + audio_amp * 0.5);
        float intensity = smoothstep(thickness, thickness * 0.3, dist);

        // Glow
        float glow = exp(-dist * dist * 200.0) * 0.3 * (1.0 + audio_amp);

        vec3 color = get_color(fi);
        final_color += vec4(color * (intensity + glow), intensity + glow * 0.5);
    }

    final_color = clamp(final_color, 0.0, 1.0);
    fragColor = final_color;
}
"""


@register
class SmokyWavesVisualization(AbstractVisualization):
    """Fluid-like wave patterns that react to audio frequency bands."""

    NAME: ClassVar[str] = "smoky_waves"
    DISPLAY_NAME: ClassVar[str] = "Smoky Waves"
    DESCRIPTION: ClassVar[str] = "Layered sinusoidal waves with audio-reactive turbulence"
    CATEGORY: ClassVar[str] = "abstract"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "wave_count": {
            "type": "int", "default": 5, "min": 2, "max": 12,
            "label": "Wave Count",
        },
        "speed": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 5.0,
            "label": "Speed",
        },
        "turbulence": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 2.0,
            "label": "Turbulence",
        },
        "thickness": {
            "type": "float", "default": 1.0, "min": 0.2, "max": 5.0,
            "label": "Line Thickness",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")

        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=SMOKY_WAVES_FRAG,
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

        fbo.use()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

        prog = self._program

        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_amplitude", frame.amplitude)
        self._set_uniform(prog, "u_bass", frame.frequency_bands.get("bass", 0.0))
        self._set_uniform(prog, "u_mid", frame.frequency_bands.get("mid", 0.0))
        self._set_uniform(prog, "u_treble", frame.frequency_bands.get("brilliance", 0.0))
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_wave_count", float(self.get_param("wave_count", 5)))
        self._set_uniform(prog, "u_speed", self.get_param("speed", 1.0))
        self._set_uniform(prog, "u_turbulence", self.get_param("turbulence", 0.5))
        self._set_uniform(prog, "u_thickness", self.get_param("thickness", 1.0))

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

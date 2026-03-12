"""Waveform visualization — displays the audio waveform as a line or filled shape."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register


@register
class WaveformVisualization(AbstractVisualization):
    """Classic waveform line visualization."""

    NAME: ClassVar[str] = "waveform"
    DISPLAY_NAME: ClassVar[str] = "Classic Waveform"
    DESCRIPTION: ClassVar[str] = "Audio waveform displayed as a line or filled shape"
    CATEGORY: ClassVar[str] = "waveform"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "line_thickness": {
            "type": "float", "default": 2.0, "min": 0.5, "max": 10.0,
            "label": "Line Thickness",
        },
        "filled": {
            "type": "bool", "default": False,
            "label": "Filled Mode",
        },
        "sample_count": {
            "type": "int", "default": 512, "min": 64, "max": 1024,
            "label": "Sample Count",
        },
        "amplitude_scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 5.0,
            "label": "Amplitude Scale",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._waveform_tex: moderngl.Texture | None = None

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        frag_src = load_shader("waveform.frag")

        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
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

        # Create 1D waveform texture (stored as Nx1 2D texture, single channel float32)
        sample_count = self.get_param("sample_count", 512)
        self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
        self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None or self._waveform_tex is None:
            return

        fbo.use()
        prog = self._program

        sample_count = self.get_param("sample_count", 512)
        amp_scale = self.get_param("amplitude_scale", 1.0)

        # Resample waveform to target sample count
        waveform = frame.waveform
        if len(waveform) > sample_count:
            indices = np.linspace(0, len(waveform) - 1, sample_count, dtype=int)
            waveform = waveform[indices]
        elif len(waveform) < sample_count:
            waveform = np.pad(waveform, (0, sample_count - len(waveform)))

        waveform = (waveform * amp_scale).astype("f4")

        # Recreate texture if sample count changed
        if self._waveform_tex.size != (sample_count, 1):
            self._waveform_tex.release()
            self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
            self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        # Upload waveform data to texture
        self._waveform_tex.write(waveform[:sample_count].tobytes())
        self._waveform_tex.use(location=0)

        self._set_uniform(prog, "u_waveform_tex", 0)
        self._set_uniform(prog, "u_sample_count", sample_count)
        self._set_uniform(prog, "u_line_thickness", self.get_param("line_thickness", 2.0))
        self._set_uniform(prog, "u_filled", 1 if self.get_param("filled", False) else 0)
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_amplitude", frame.amplitude)
        self._set_uniform(prog, "u_time", frame.timestamp)

        color = self.params.params.get("_primary_color", (0.0, 1.0, 0.67))
        self._set_uniform(prog, "u_color", color)

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._waveform_tex:
            self._waveform_tex.release()
        if self._program:
            self._program.release()

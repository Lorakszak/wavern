"""Circular spectrum visualization — radial bar spectrum analyzer."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register
from wavern.visualizations.spectrum_bars import _log_resample


@register
class CircularSpectrumVisualization(AbstractVisualization):
    """Radial spectrum analyzer with bars arranged in a circle."""

    NAME: ClassVar[str] = "circular_spectrum"
    DISPLAY_NAME: ClassVar[str] = "Circular Spectrum"
    DESCRIPTION: ClassVar[str] = "Spectrum bars arranged radially around a circle"
    CATEGORY: ClassVar[str] = "spectrum"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "bar_count": {
            "type": "int", "default": 64, "min": 16, "max": 128,
            "label": "Bar Count",
        },
        "inner_radius": {
            "type": "float", "default": 0.2, "min": 0.05, "max": 0.5,
            "label": "Inner Radius",
        },
        "bar_length": {
            "type": "float", "default": 0.3, "min": 0.05, "max": 0.6,
            "label": "Bar Length",
        },
        "rotation_speed": {
            "type": "float", "default": 0.2, "min": 0.0, "max": 2.0,
            "label": "Rotation Speed",
        },
        "gravity": {
            "type": "float", "default": 0.85, "min": 0.0, "max": 0.99,
            "label": "Gravity (smoothing)",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._prev_magnitudes: np.ndarray | None = None

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        frag_src = load_shader("circular.frag")

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

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None:
            return

        bar_count = self.get_param("bar_count", 64)
        gravity = self.get_param("gravity", 0.85)

        # Resample to bar_count using log scale
        n = len(frame.fft_magnitudes)
        magnitudes = _log_resample(frame.fft_magnitudes, n, bar_count)

        # Apply gravity
        if self._prev_magnitudes is not None and len(self._prev_magnitudes) == bar_count:
            magnitudes = np.maximum(magnitudes, self._prev_magnitudes * gravity)
        self._prev_magnitudes = magnitudes.copy()

        # Normalize
        max_val = max(np.max(magnitudes), 1e-10)
        magnitudes = np.clip(magnitudes / max_val, 0.0, 1.0)

        fbo.use()
        prog = self._program

        padded = np.zeros(128, dtype="f4")
        padded[:bar_count] = magnitudes[:bar_count]
        self._write_uniform(prog, "u_magnitudes", padded.tobytes())

        self._set_uniform(prog, "u_bar_count", bar_count)
        self._set_uniform(prog, "u_inner_radius", self.get_param("inner_radius", 0.2))
        self._set_uniform(prog, "u_bar_length", self.get_param("bar_length", 0.3))
        self._set_uniform(prog, "u_rotation_speed", self.get_param("rotation_speed", 0.2))
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_amplitude", frame.amplitude)

        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67), (1.0, 0.0, 0.67)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

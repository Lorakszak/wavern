"""Circular spectrum visualization — radial bar spectrum analyzer."""

from typing import Any, ClassVar

import math

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.image_mixin import ImageTextureMixin
from wavern.visualizations.registry import register
from wavern.visualizations.spectrum_bars import _log_resample


@register
class CircularSpectrumVisualization(ImageTextureMixin, AbstractVisualization):
    """Radial spectrum analyzer with bars arranged in a circle."""

    NAME: ClassVar[str] = "circular_spectrum"
    DISPLAY_NAME: ClassVar[str] = "Circular Spectrum"
    DESCRIPTION: ClassVar[str] = "Spectrum bars arranged radially around a circle"
    CATEGORY: ClassVar[str] = "spectrum"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "bar_count": {
            "type": "int", "default": 64, "min": 8, "max": 256,
            "label": "Bar Count",
            "description": "Number of radial bars around the circle.",
        },
        "inner_radius": {
            "type": "float", "default": 0.2, "min": 0.01, "max": 0.8,
            "label": "Inner Radius",
            "description": "Radius of the inner circle where bars start.",
        },
        "bar_length": {
            "type": "float", "default": 0.3, "min": 0.01, "max": 1.0,
            "label": "Bar Length",
            "description": "Maximum length of bars extending outward from the circle.",
        },
        "rotation_speed": {
            "type": "float", "default": 0.2, "min": 0.0, "max": 10.0,
            "label": "Rotation Speed",
            "description": "Speed of continuous rotation. 0 = stationary.",
        },
        "gravity": {
            "type": "float", "default": 0.85, "min": 0.0, "max": 0.99,
            "label": "Gravity (smoothing)",
            "description": "How slowly bars fall after a peak. Higher = slower decay.",
        },
        "bar_spacing": {
            "type": "float", "default": 0.25, "min": 0.0, "max": 0.9,
            "step": 0.01,
            "label": "Bar Spacing",
            "description": "Gap between bars as a fraction of slot width (0.0 = no gap, 0.9 = very wide gap).",
        },
        "glow_intensity": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 2.0,
            "label": "Glow Intensity",
            "description": "Strength of tip glow and inner ring glow effects.",
        },
        "rotation_offset": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 360.0,
            "label": "Rotation Offset",
            "description": "Static rotation angle in degrees.",
        },
        "center_x": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Center X",
            "description": "Horizontal center offset for the circle.",
        },
        "center_y": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Center Y",
            "description": "Vertical center offset for the circle.",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Scale",
            "description": "Zoom level. Values below 1.0 zoom in, above 1.0 zoom out.",
        },
        "mirror_spectrum": {
            "type": "bool", "default": False,
            "label": "Mirror Spectrum",
            "description": "Mirror one half of the spectrum to both sides.",
        },
        "mirror_half": {
            "type": "choice", "default": "left",
            "choices": ["left", "right"],
            "label": "Mirror Half",
            "description": "Which half to use as source (left=low freq, right=high freq).",
        },
        "bar_roundness": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 1.0,
            "label": "Bar Roundness",
            "description": "Bar tip rounding. 0=sharp, 1=fully rounded.",
        },
        "shadow_enabled": {
            "type": "bool", "default": False,
            "label": "Shadow",
            "description": "Enable bar drop shadow.",
        },
        "shadow_color": {
            "type": "color", "default": "#000000",
            "label": "Shadow Color",
            "description": "Shadow color.",
        },
        "shadow_opacity": {
            "type": "float", "default": 0.4, "min": 0.0, "max": 1.0,
            "label": "Shadow Opacity",
            "description": "Shadow opacity.",
        },
        "shadow_offset_x": {
            "type": "float", "default": 0.005, "min": -0.1, "max": 0.1,
            "label": "Shadow Offset X",
            "description": "Horizontal shadow offset.",
        },
        "shadow_offset_y": {
            "type": "float", "default": -0.005, "min": -0.1, "max": 0.1,
            "label": "Shadow Offset Y",
            "description": "Vertical shadow offset.",
        },
        "shadow_size": {
            "type": "float", "default": 1.0, "min": 0.5, "max": 3.0,
            "label": "Shadow Size",
            "description": "Shadow scale relative to bar.",
        },
        "shadow_blur": {
            "type": "float", "default": 0.005, "min": 0.0, "max": 0.05,
            "label": "Shadow Blur",
            "description": "Shadow edge softness.",
        },
        "inner_image_path": {
            "type": "file", "default": "",
            "label": "Inner Image",
            "description": "Image displayed inside the inner circle.",
            "file_filter": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        },
        "inner_image_padding": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 0.5,
            "label": "Image Padding",
            "description": "Shrink image inward from circle border.",
        },
        "inner_image_beat_bounce": {
            "type": "bool", "default": False,
            "label": "Image Beat Bounce",
            "description": "Image enlarges on detected beats.",
        },
        "inner_image_bounce_strength": {
            "type": "float", "default": 0.15, "min": 0.0, "max": 0.5,
            "label": "Image Bounce Strength",
            "description": "How much the image enlarges on beat.",
        },
        "inner_image_bounce_zoom": {
            "type": "bool", "default": False,
            "label": "Bounce Zoom Mode",
            "description": "Zoom into image on bounce instead of scaling it.",
        },
        "shape_beat_bounce": {
            "type": "bool", "default": False,
            "label": "Shape Beat Bounce",
            "description": "Inner circle pulses on detected beats.",
        },
        "shape_bounce_strength": {
            "type": "float", "default": 0.15, "min": 0.0, "max": 0.5,
            "label": "Shape Bounce Strength",
            "description": "How much the inner circle grows on beat.",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._prev_magnitudes: np.ndarray | None = None
        self._init_image_state()

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
        self._ensure_fallback_texture(self.ctx)

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

        padded = np.zeros(256, dtype="f4")
        padded[:bar_count] = magnitudes[:bar_count]
        self._write_uniform(prog, "u_magnitudes", padded.tobytes())

        self._set_uniform(prog, "u_bar_count", bar_count)
        self._set_uniform(prog, "u_inner_radius", self.get_param("inner_radius", 0.2))
        self._set_uniform(prog, "u_bar_length", self.get_param("bar_length", 0.3))
        self._set_uniform(prog, "u_rotation_speed", self.get_param("rotation_speed", 0.2))
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_amplitude", frame.amplitude)
        self._set_uniform(prog, "u_bar_spacing", self.get_param("bar_spacing", 0.25))
        self._set_uniform(prog, "u_glow_intensity", self.get_param("glow_intensity", 0.5))
        self._set_uniform(prog, "u_rotation_offset", math.radians(self.get_param("rotation_offset", 0.0)))
        self._set_uniform(prog, "u_center_offset", (self.get_param("center_x", 0.0), self.get_param("center_y", 0.0)))
        self._set_uniform(prog, "u_viz_scale", self.get_param("scale", 1.0))
        self._set_uniform(prog, "u_mirror_spectrum",
                          1 if self.get_param("mirror_spectrum", False) else 0)
        self._set_uniform(prog, "u_mirror_half",
                          0 if self.get_param("mirror_half", "left") == "left" else 1)

        # Bar roundness
        self._set_uniform(prog, "u_bar_roundness", self.get_param("bar_roundness", 0.0))

        # Shadow uniforms
        self._set_uniform(
            prog, "u_shadow_enabled",
            1 if self.get_param("shadow_enabled", False) else 0,
        )
        shadow_hex = self.get_param("shadow_color", "#000000")
        sr = int(shadow_hex[1:3], 16) / 255.0
        sg = int(shadow_hex[3:5], 16) / 255.0
        sb = int(shadow_hex[5:7], 16) / 255.0
        self._set_uniform(prog, "u_shadow_color", (sr, sg, sb))
        self._set_uniform(prog, "u_shadow_opacity", self.get_param("shadow_opacity", 0.4))
        self._set_uniform(prog, "u_shadow_offset", (
            self.get_param("shadow_offset_x", 0.005),
            self.get_param("shadow_offset_y", -0.005),
        ))
        self._set_uniform(prog, "u_shadow_size", self.get_param("shadow_size", 1.0))
        self._set_uniform(prog, "u_shadow_blur", self.get_param("shadow_blur", 0.005))

        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67), (1.0, 0.0, 0.67)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        self._bind_image_uniforms(prog, frame, self.get_param, self._set_uniform, self.ctx)

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def cleanup(self) -> None:
        self._release_image_texture()
        self._release_fallback_texture()
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

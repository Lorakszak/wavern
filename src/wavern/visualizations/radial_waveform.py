"""Radial waveform visualization — audio waveform wrapped around a circle."""

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


@register
class RadialWaveformVisualization(ImageTextureMixin, AbstractVisualization):
    """Audio waveform wrapped around a circle with optional inner image."""

    NAME: ClassVar[str] = "radial_waveform"
    DISPLAY_NAME: ClassVar[str] = "Radial Waveform"
    DESCRIPTION: ClassVar[str] = "Audio waveform wrapped around a circle"
    CATEGORY: ClassVar[str] = "waveform"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "sample_count": {
            "type": "int", "default": 256, "min": 64, "max": 1024,
            "label": "Sample Count",
            "description": "Number of waveform samples around the circle. Higher = more detailed waveform.",
        },
        "inner_radius": {
            "type": "float", "default": 0.2, "min": 0.01, "max": 0.8,
            "label": "Inner Radius",
            "description": "Radius of the base circle.",
        },
        "wave_amplitude": {
            "type": "float", "default": 0.3, "min": 0.01, "max": 1.0,
            "label": "Wave Amplitude",
            "description": "How far the waveform extends outward from the circle.",
        },
        "line_thickness": {
            "type": "float", "default": 2.0, "min": 0.5, "max": 20.0,
            "label": "Line Thickness",
            "description": "Thickness of the waveform line in pixels.",
        },
        "smoothing": {
            "type": "int", "default": 8, "min": 1, "max": 64,
            "label": "Smoothing",
            "description": "Box filter kernel size for waveform smoothing. Higher = smoother curve.",
        },
        "filled": {
            "type": "bool", "default": False,
            "label": "Filled Mode",
            "description": "Fill the area between the circle and waveform.",
        },
        "rotation_speed": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 10.0,
            "label": "Rotation Speed",
            "description": "Speed of continuous rotation. 0 = stationary.",
        },
        "rotation_direction": {
            "type": "choice", "default": "clockwise",
            "choices": ["clockwise", "counterclockwise"],
            "label": "Rotation Direction",
            "description": "Direction of continuous rotation.",
        },
        "mirror_mode": {
            "type": "choice", "default": "none",
            "choices": ["none", "mirror", "duplicate"],
            "label": "Mirror Mode",
            "description": "none = full waveform around circle. mirror = fold second half symmetrically. duplicate = first half repeated twice.",
        },
        "glow_intensity": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 2.0,
            "label": "Glow Intensity",
            "description": "Strength of the glow effect around the waveform line.",
        },
        "rotation_offset": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 360.0,
            "label": "Rotation Offset",
            "description": "Static rotation angle in degrees.",
        },
        "center_x": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Center X",
            "description": "Horizontal center offset.",
        },
        "center_y": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Center Y",
            "description": "Vertical center offset.",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Scale",
            "description": "Zoom level. Values below 1.0 zoom in, above 1.0 zoom out.",
        },
        "inner_image_path": {
            "type": "file", "default": "",
            "label": "Inner Image",
            "description": "Image displayed inside the circle.",
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
        "inner_image_rotation_speed": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 10.0,
            "label": "Image Rotation Speed",
            "description": "Speed of inner image rotation. 0 = stationary.",
        },
        "inner_image_rotation_direction": {
            "type": "choice", "default": "clockwise",
            "choices": ["clockwise", "counterclockwise"],
            "label": "Image Rotation Direction",
            "description": "Direction of inner image rotation.",
        },
        "shape_beat_bounce": {
            "type": "bool", "default": True,
            "label": "Shape Beat Bounce",
            "description": "Circle pulses outward on detected beats.",
        },
        "shape_bounce_strength": {
            "type": "float", "default": 0.15, "min": 0.0, "max": 1.0,
            "label": "Shape Bounce Strength",
            "description": "How much the circle grows on beat.",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._waveform_tex: moderngl.Texture | None = None
        self._init_image_state()

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        frag_src = load_shader("radial_waveform.frag")

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

        sample_count = self.get_param("sample_count", 256)
        self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
        self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self._ensure_fallback_texture(self.ctx)

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

        sample_count = self.get_param("sample_count", 256)
        smoothing_kernel = self.get_param("smoothing", 8)

        # Resample waveform to target sample count
        waveform = frame.waveform
        if len(waveform) > sample_count:
            indices = np.linspace(0, len(waveform) - 1, sample_count, dtype=int)
            waveform = waveform[indices]
        elif len(waveform) < sample_count:
            waveform = np.pad(waveform, (0, sample_count - len(waveform)))

        # Apply box filter smoothing
        if smoothing_kernel > 1:
            kernel = np.ones(smoothing_kernel, dtype="f4") / smoothing_kernel
            waveform = np.convolve(waveform, kernel, mode="same")

        waveform = waveform.astype("f4")

        # Recreate texture if sample count changed
        if self._waveform_tex.size != (sample_count, 1):
            self._waveform_tex.release()
            self._waveform_tex = self.ctx.texture((sample_count, 1), 1, dtype="f4")
            self._waveform_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self._waveform_tex.write(waveform[:sample_count].tobytes())
        self._waveform_tex.use(location=0)

        self._set_uniform(prog, "u_waveform_tex", 0)
        self._set_uniform(prog, "u_sample_count", sample_count)
        self._set_uniform(prog, "u_inner_radius", self.get_param("inner_radius", 0.2))
        self._set_uniform(prog, "u_wave_amplitude", self.get_param("wave_amplitude", 0.3))
        self._set_uniform(prog, "u_line_thickness", self.get_param("line_thickness", 2.0))
        self._set_uniform(prog, "u_filled", 1 if self.get_param("filled", False) else 0)
        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_time", frame.timestamp)
        self._set_uniform(prog, "u_amplitude", frame.amplitude_envelope)
        self._set_uniform(prog, "u_glow_intensity", self.get_param("glow_intensity", 0.5))
        self._set_uniform(prog, "u_rotation_offset",
                          math.radians(self.get_param("rotation_offset", 0.0)))

        rot_speed = self.get_param("rotation_speed", 0.0)
        rot_dir = self.get_param("rotation_direction", "clockwise")
        if rot_dir == "counterclockwise":
            rot_speed = -rot_speed
        self._set_uniform(prog, "u_rotation_speed", rot_speed)

        self._set_uniform(prog, "u_center_offset", (
            self.get_param("center_x", 0.0),
            self.get_param("center_y", 0.0),
        ))
        self._set_uniform(prog, "u_viz_scale", self.get_param("scale", 1.0))

        mirror_mode = self.get_param("mirror_mode", "none")
        mirror_int = {"none": 0, "mirror": 1, "duplicate": 2}.get(mirror_mode, 0)
        self._set_uniform(prog, "u_mirror_mode", mirror_int)

        # Colors
        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67), (1.0, 0.0, 0.67)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        # Image uniforms (handles texture binding at location 1)
        self._bind_image_uniforms(prog, frame, self.get_param, self._set_uniform, self.ctx)

        img_rot_speed = self.get_param("inner_image_rotation_speed", 0.0)
        img_rot_dir = self.get_param("inner_image_rotation_direction", "clockwise")
        img_rot_sign = 1.0 if img_rot_dir == "clockwise" else -1.0
        self._set_uniform(prog, "u_image_rotation",
                          frame.timestamp * img_rot_speed * img_rot_sign)

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def cleanup(self) -> None:
        self._release_image_texture()
        self._release_fallback_texture()
        if self._waveform_tex:
            self._waveform_tex.release()
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

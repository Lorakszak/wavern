"""Spectrum bars visualization — vertical bars representing frequency magnitudes."""

from typing import Any, ClassVar

import math

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.utils.color import hex_to_rgb
from wavern.visualizations.registry import register


def _log_resample(
    magnitudes: np.ndarray, n: int, bar_count: int, max_bin: int = 0,
) -> np.ndarray:
    """Resample FFT magnitudes into bar_count bins using logarithmic spacing.

    Ensures each bar maps to at least one unique FFT bin so low-frequency
    bars don't merge together.

    Args:
        magnitudes: FFT magnitude array.
        n: Total number of FFT bins available.
        bar_count: Number of output bars.
        max_bin: If >0, only map bins up to this index (frequency limit).
    """
    effective_n = min(n, max_bin) if max_bin > 0 else n
    # Compute log-spaced bin edges (skip DC at bin 0)
    edges = np.logspace(0, np.log10(effective_n), bar_count + 1)
    edges = np.round(edges).astype(int)
    edges[0] = max(edges[0], 1)
    edges[-1] = effective_n

    # Ensure strictly increasing: each edge must be > previous
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1

    # If we overshot effective_n, trim the bar count to what actually fits
    if edges[-1] > effective_n:
        cutoff = int(np.searchsorted(edges, effective_n, side="right"))
        edges = edges[:cutoff]
        edges[-1] = n

    actual_bars = len(edges) - 1
    result = np.zeros(bar_count, dtype="f4")
    for i in range(actual_bars):
        result[i] = np.mean(magnitudes[edges[i]:edges[i + 1]])
    return result


@register
class SpectrumBarsVisualization(AbstractVisualization):
    """Vertical bar spectrum analyzer."""

    NAME: ClassVar[str] = "spectrum_bars"
    DISPLAY_NAME: ClassVar[str] = "Spectrum Bars"
    DESCRIPTION: ClassVar[str] = "Classic vertical bar spectrum analyzer"
    CATEGORY: ClassVar[str] = "spectrum"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "frequency_limit": {
            "type": "bool", "default": False,
            "label": "Frequency Limit",
            "description": "Cap the displayed frequency range. When off, bars cover the full spectrum up to 22 kHz — where the upper bars are often silent because most music has little energy above ~4 kHz. Enable this and set Max Frequency to focus bars on the active range.",
        },
        "max_frequency": {
            "type": "int", "default": 16000, "min": 2000, "max": 22050,
            "label": "Max Frequency (Hz)",
            "description": "Upper frequency limit in Hz. Bars will be distributed from ~20 Hz up to this value. Lower values concentrate bars on bass/mids; raise toward 22050 to show the full spectrum.",
        },
        "bar_count": {
            "type": "int", "default": 64, "min": 4, "max": 256,
            "label": "Bar Count",
            "description": "Number of frequency bars. More bars = finer frequency resolution.",
        },
        "bar_spacing": {
            "type": "float", "default": 0.25, "min": 0.0, "max": 0.9,
            "step": 0.01,
            "label": "Bar Spacing",
            "description": "Gap between bars as a fraction of slot width (0.0 = no gap, 0.9 = very wide gap).",
        },
        "mirror": {
            "type": "bool", "default": False,
            "label": "Mirror",
            "description": "Mirror bars vertically around the center line.",
        },
        "min_bar_height": {
            "type": "float", "default": 0.01, "min": 0.0, "max": 0.1,
            "label": "Min Height",
            "description": "Minimum bar height when silent. Keeps bars visible at low volume.",
        },
        "max_bar_height": {
            "type": "float", "default": 0.95, "min": 0.1, "max": 1.0,
            "label": "Max Height",
            "description": "Maximum bar height at peak volume.",
        },
        "frequency_scale": {
            "type": "choice", "default": "logarithmic",
            "choices": ["linear", "logarithmic"],
            "label": "Frequency Scale",
            "description": "Logarithmic groups low frequencies together (natural). Linear spaces equally.",
        },
        "gravity": {
            "type": "float", "default": 0.85, "min": 0.0, "max": 0.99,
            "label": "Gravity (smoothing)",
            "description": "How slowly bars fall after a peak. Higher = slower decay.",
        },
        "color_mode": {
            "type": "choice", "default": "position",
            "choices": ["position", "height"],
            "label": "Color Mode",
            "description": "Color by bar position (left-to-right gradient) or by bar height.",
        },
        "height_reference": {
            "type": "choice", "default": "per_bar",
            "choices": ["per_bar", "universal"],
            "label": "Height Reference",
            "description": "Per-bar: gradient fills each bar independently. Universal: fixed color at each height.",
        },
        "intensity": {
            "type": "float", "default": 1.0, "min": 0.5, "max": 2.0,
            "label": "Intensity",
            "description": "Brightness multiplier for bar colors.",
        },
        "position_x": {
            "type": "float", "default": 0.5, "min": -0.25, "max": 1.25,
            "label": "Position X",
            "description": "Horizontal position (0.0 = left edge, 1.0 = right edge).",
        },
        "position_y": {
            "type": "float", "default": 0.0, "min": -0.25, "max": 1.25,
            "label": "Position Y",
            "description": "Vertical position (0.0 = bottom edge, 1.0 = top edge).",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Scale",
            "description": "Zoom level. Values below 1.0 zoom in, above 1.0 zoom out.",
        },
        "rotation": {
            "type": "float", "default": 0.0, "min": -180.0, "max": 180.0,
            "label": "Rotation",
            "description": "Rotation angle in degrees.",
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
            "disabled": True,
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
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._prev_magnitudes: np.ndarray | None = None

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        frag_src = load_shader("spectrum_bars.frag")

        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        # Fullscreen quad
        vertices = np.array([
            # position    texcoord
            -1.0, -1.0,   0.0, 0.0,
             1.0, -1.0,   1.0, 0.0,
            -1.0,  1.0,   0.0, 1.0,
             1.0,  1.0,   1.0, 1.0,
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

        # Compute frequency limit bin
        max_bin = 0
        if self.get_param("frequency_limit", False):
            max_freq = self.get_param("max_frequency", 16000)
            n_bins = len(frame.fft_magnitudes_db)
            nyquist = frame.fft_frequencies[-1] if len(frame.fft_frequencies) > 0 else 22050.0
            max_bin = max(1, int(max_freq / nyquist * n_bins))

        # Resample dB-scaled FFT magnitudes to bar_count bins
        magnitudes = self._resample_magnitudes(frame.fft_magnitudes_db, bar_count, max_bin=max_bin)

        # Apply gravity (smooth decay)
        if self._prev_magnitudes is not None and len(self._prev_magnitudes) == bar_count:
            magnitudes = np.maximum(magnitudes, self._prev_magnitudes * gravity)
        self._prev_magnitudes = magnitudes.copy()

        magnitudes = np.clip(magnitudes, 0.0, 1.0)

        # Set uniforms
        fbo.use()
        prog = self._program

        # Upload magnitudes (pad to 256)
        padded = np.zeros(256, dtype="f4")
        padded[:bar_count] = magnitudes[:bar_count]
        self._write_uniform(prog, "u_magnitudes", padded.tobytes())

        self._set_uniform(prog, "u_bar_count", bar_count)
        self._set_uniform(prog, "u_bar_spacing", self.get_param("bar_spacing", 0.25))
        self._set_uniform(prog, "u_min_height", self.get_param("min_bar_height", 0.01))
        self._set_uniform(prog, "u_max_height", self.get_param("max_bar_height", 0.95))
        self._set_uniform(prog, "u_mirror", 1 if self.get_param("mirror", False) else 0)
        self._set_uniform(prog, "u_color_mode", 0 if self.get_param("color_mode", "position") == "position" else 1)
        self._set_uniform(prog, "u_height_reference",
                          0 if self.get_param("height_reference", "per_bar") == "per_bar" else 1)
        self._set_uniform(prog, "u_intensity", self.get_param("intensity", 1.0))
        self._set_uniform(prog, "u_mirror_spectrum",
                          1 if self.get_param("mirror_spectrum", False) else 0)
        self._set_uniform(prog, "u_mirror_half",
                          0 if self.get_param("mirror_half", "left") == "left" else 1)

        self._set_uniform(prog, "u_position", (self.get_param("position_x", 0.5), self.get_param("position_y", 0.5)))
        self._set_uniform(prog, "u_scale", self.get_param("scale", 1.0))
        self._set_uniform(prog, "u_rotation", math.radians(self.get_param("rotation", 0.0)))

        # Bar roundness
        self._set_uniform(prog, "u_bar_roundness", self.get_param("bar_roundness", 0.0))

        # Shadow uniforms
        self._set_uniform(
            prog, "u_shadow_enabled",
            1 if self.get_param("shadow_enabled", False) else 0,
        )
        shadow_hex = self.get_param("shadow_color", "#000000")
        sr, sg, sb = hex_to_rgb(shadow_hex)
        self._set_uniform(prog, "u_shadow_color", (sr, sg, sb))
        self._set_uniform(prog, "u_shadow_opacity", self.get_param("shadow_opacity", 0.4))
        self._set_uniform(prog, "u_shadow_offset", (
            self.get_param("shadow_offset_x", 0.005),
            self.get_param("shadow_offset_y", -0.005),
        ))
        self._set_uniform(prog, "u_shadow_size", self.get_param("shadow_size", 1.0))
        self._set_uniform(prog, "u_shadow_blur", self.get_param("shadow_blur", 0.005))

        # Upload colors from preset
        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67), (1.0, 0.0, 0.67)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def update_params(self, params: VisualizationParams) -> None:
        super().update_params(params)
        # Reset gravity state if bar count changed
        new_count = params.params.get("bar_count", 64)
        if self._prev_magnitudes is not None and len(self._prev_magnitudes) != new_count:
            self._prev_magnitudes = None

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

    def _resample_magnitudes(
        self, magnitudes: np.ndarray, bar_count: int, max_bin: int = 0,
    ) -> np.ndarray:
        """Resample FFT magnitudes to the desired number of bars."""
        scale = self.get_param("frequency_scale", "logarithmic")
        n = len(magnitudes)

        if scale == "logarithmic":
            return _log_resample(magnitudes, n, bar_count, max_bin=max_bin)
        else:
            # Linear binning
            effective_n = min(n, max_bin) if max_bin > 0 else n
            indices = np.linspace(0, effective_n - 1, bar_count, dtype=int)
            return magnitudes[indices].astype("f4")

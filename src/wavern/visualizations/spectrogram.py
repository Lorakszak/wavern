"""Spectrogram visualization — scrolling frequency heatmap."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

_N_BINS: int = 256  # Fixed display resolution (frequency axis)

_COLOR_MAP_IDS: dict[str, int] = {
    "palette": 0,
    "inferno": 1,
    "magma": 2,
    "viridis": 3,
    "plasma": 4,
    "grayscale": 5,
}

_SCROLL_DIR_IDS: dict[str, int] = {
    "left": 0,
    "right": 1,
    "up": 2,
    "down": 3,
}


def _resample_spectrum(
    magnitudes_db: np.ndarray,
    frequencies: np.ndarray,
    n_out: int,
    scale: str,
    min_freq: float,
    max_freq: float,
) -> np.ndarray:
    """Resample FFT magnitudes to n_out display bins on the requested scale.

    Args:
        magnitudes_db: 0–1 normalised dB magnitudes from FrameAnalysis.
        frequencies: Corresponding Hz values for each bin.
        n_out: Number of output bins.
        scale: "linear", "logarithmic", or "mel".
        min_freq: Minimum frequency in Hz.
        max_freq: Maximum frequency in Hz.

    Returns:
        Float32 array of length n_out, values 0–1.
    """
    min_freq = max(min_freq, float(frequencies[1]) if len(frequencies) > 1 else 20.0)
    max_freq = min(max_freq, float(frequencies[-1]))

    if scale == "logarithmic":
        target = np.logspace(np.log10(max(min_freq, 1.0)), np.log10(max_freq), n_out)
    elif scale == "mel":
        min_mel = 2595.0 * np.log10(1.0 + min_freq / 700.0)
        max_mel = 2595.0 * np.log10(1.0 + max_freq / 700.0)
        mel_pts = np.linspace(min_mel, max_mel, n_out)
        target = 700.0 * (10.0 ** (mel_pts / 2595.0) - 1.0)
    else:  # linear
        target = np.linspace(min_freq, max_freq, n_out)

    return np.interp(target, frequencies, magnitudes_db).astype("f4")


@register
class SpectrogramVisualization(AbstractVisualization):
    """Scrolling frequency-vs-time heatmap with configurable colormaps."""

    NAME: ClassVar[str] = "spectrogram"
    DISPLAY_NAME: ClassVar[str] = "Spectrogram (Alpha)"
    DESCRIPTION: ClassVar[str] = "Scrolling frequency heatmap — color encodes magnitude over time"
    CATEGORY: ClassVar[str] = "spectrum"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "scroll_direction": {
            "type": "choice", "default": "left",
            "choices": ["left", "right", "up", "down"],
            "label": "Scroll Direction",
            "description": "Direction the heatmap scrolls. New data enters from the opposite edge.",
        },
        "scroll_speed": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 5.0,
            "label": "Scroll Speed",
            "description": "Columns written per frame. 1=one per frame, 2=two per frame (faster), 0.5=one every two frames (slower).",
        },
        "frequency_scale": {
            "type": "choice", "default": "logarithmic",
            "choices": ["linear", "logarithmic", "mel"],
            "label": "Frequency Scale",
            "description": "How frequency bins are distributed along the frequency axis.",
        },
        "frequency_limit": {
            "type": "bool", "default": False,
            "label": "Frequency Limit",
            "description": "Cap the displayed frequency range to Max Frequency.",
        },
        "min_frequency": {
            "type": "int", "default": 20, "min": 20, "max": 2000,
            "label": "Min Frequency (Hz)",
            "description": "Lowest frequency to display. Raise to cut sub-bass rumble.",
        },
        "max_frequency": {
            "type": "int", "default": 16000, "min": 2000, "max": 22050,
            "label": "Max Frequency (Hz)",
            "description": "Highest frequency displayed when Frequency Limit is on.",
        },
        "color_map": {
            "type": "choice", "default": "inferno",
            "choices": ["palette", "inferno", "magma", "viridis", "plasma", "grayscale"],
            "label": "Color Map",
            "description": "Color mapping for magnitude values. Scientific maps (inferno/magma/viridis/plasma) are perceptually uniform. 'palette' uses the preset colour palette.",
        },
        "brightness": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 3.0,
            "label": "Brightness",
            "description": "Multiplier applied to magnitude values before colormapping. Raise to make quiet sounds more visible.",
        },
        "contrast": {
            "type": "float", "default": 1.2, "min": 0.1, "max": 3.0,
            "label": "Contrast",
            "description": "Contrast around the midpoint. Values above 1 push bright and dark apart.",
        },
        "saturation": {
            "type": "float", "default": 1.0, "min": 0.0, "max": 2.0,
            "label": "Saturation",
            "description": "Colour saturation. 0 = greyscale, 1 = unchanged, 2 = doubled.",
        },
        "history_length": {
            "type": "int", "default": 256, "min": 64, "max": 1024,
            "label": "History Length",
            "description": "Number of frames stored in history. More = longer time window, larger GPU texture.",
        },
        "blur": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 3.0,
            "label": "Blur",
            "description": "Gaussian blur radius (5×5 kernel). Smooths the heatmap.",
        },
        "bar_separation": {
            "type": "bool", "default": False,
            "label": "Bar Separation",
            "description": "Draw thin dark lines between frequency bins, making each bin a discrete bar.",
        },
        "offset_x": {
            "type": "float", "default": 0.0, "min": -0.5, "max": 0.5,
            "label": "Offset X",
            "description": "Horizontal position offset.",
        },
        "offset_y": {
            "type": "float", "default": 0.0, "min": -0.5, "max": 0.5,
            "label": "Offset Y",
            "description": "Vertical position offset.",
        },
        "scale": {
            "type": "float", "default": 1.0, "min": 0.5, "max": 2.0,
            "label": "Scale",
            "description": "Zoom level.",
        },
    }

    # Params whose change requires a full history reset
    _RESET_PARAMS: frozenset[str] = frozenset({
        "frequency_scale", "frequency_limit", "min_frequency",
        "max_frequency", "history_length",
    })

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None
        self._history_tex: moderngl.Texture | None = None
        self._write_pos: int = 0
        self._scroll_accum: float = 0.0
        self._prev_timestamp: float = 0.0

    def initialize(self) -> None:
        vert_src = load_shader("common.vert")
        frag_src = load_shader("spectrogram.frag")

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

        self._create_history_texture()

    def _create_history_texture(self) -> None:
        """Allocate the ring-buffer history texture and zero it."""
        if self._history_tex is not None:
            self._history_tex.release()
            self._history_tex = None

        history_length = self.get_param("history_length", 256)
        zeros = np.zeros(history_length * _N_BINS, dtype="f4")
        self._history_tex = self.ctx.texture(
            (history_length, _N_BINS), 1, zeros.tobytes(), dtype="f4",
        )
        self._history_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._history_tex.repeat_x = True
        self._history_tex.repeat_y = False
        self._write_pos = 0
        self._scroll_accum = 0.0

    def update_params(self, params: VisualizationParams) -> None:
        """Update params; reset history if any frequency/history param changed."""
        old_vals = {k: self.get_param(k) for k in self._RESET_PARAMS}
        self.params = params
        new_vals = {k: self.get_param(k) for k in self._RESET_PARAMS}

        if old_vals != new_vals:
            self._create_history_texture()

    def _compute_column(self, frame: FrameAnalysis) -> np.ndarray:
        """Resample current FFT to _N_BINS display bins."""
        freq_limit = self.get_param("frequency_limit", False)
        max_freq = self.get_param("max_frequency", 16000) if freq_limit else float(frame.fft_frequencies[-1])
        min_freq = float(self.get_param("min_frequency", 20))

        return _resample_spectrum(
            frame.fft_magnitudes_db,
            frame.fft_frequencies,
            _N_BINS,
            self.get_param("frequency_scale", "logarithmic"),
            min_freq,
            max_freq,
        )

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None or self._history_tex is None:
            return

        history_length = self.get_param("history_length", 256)
        scroll_speed = self.get_param("scroll_speed", 1.0)

        # Accumulator-based scroll speed: advance ring buffer N columns per frame
        self._scroll_accum += scroll_speed
        n_steps = int(self._scroll_accum)
        self._scroll_accum -= float(n_steps)

        if n_steps > 0:
            col = self._compute_column(frame)
            # Cap steps so we don't overwrite the entire buffer with one frame
            n_steps = min(n_steps, history_length // 4)
            for _ in range(n_steps):
                self._history_tex.write(
                    col.tobytes(),
                    viewport=(self._write_pos, 0, 1, _N_BINS),
                )
                self._write_pos = (self._write_pos + 1) % history_length

        fbo.use()
        prog = self._program

        self._history_tex.use(location=0)
        self._set_uniform(prog, "u_history_tex", 0)
        self._set_uniform(prog, "u_history_length", history_length)
        self._set_uniform(prog, "u_n_bins", _N_BINS)
        # write_pos is now the NEXT position to write; most-recently written = (write_pos - 1) % H
        newest = (self._write_pos - 1) % history_length
        self._set_uniform(prog, "u_write_pos", newest)

        scroll_dir = self.get_param("scroll_direction", "left")
        self._set_uniform(prog, "u_scroll_dir", _SCROLL_DIR_IDS.get(scroll_dir, 0))

        color_map = self.get_param("color_map", "inferno")
        self._set_uniform(prog, "u_color_map", _COLOR_MAP_IDS.get(color_map, 1))

        self._set_uniform(prog, "u_brightness", self.get_param("brightness", 1.0))
        self._set_uniform(prog, "u_contrast", self.get_param("contrast", 1.2))
        self._set_uniform(prog, "u_saturation", self.get_param("saturation", 1.0))
        self._set_uniform(prog, "u_blur", self.get_param("blur", 0.0))
        self._set_uniform(prog, "u_bar_separation",
                          1 if self.get_param("bar_separation", False) else 0)

        self._set_uniform(prog, "u_resolution", resolution)
        self._set_uniform(prog, "u_offset", (
            self.get_param("offset_x", 0.0),
            self.get_param("offset_y", 0.0),
        ))
        self._set_uniform(prog, "u_viz_scale", self.get_param("scale", 1.0))

        # Colors for "palette" mode
        colors = self.params.params.get("_colors", [(1.0, 0.5, 0.0), (1.0, 0.0, 0.0)])
        color_data = np.zeros((8, 3), dtype="f4")
        for i in range(min(len(colors), 8)):
            color_data[i] = colors[i]
        self._write_uniform(prog, "u_colors", color_data.tobytes())
        self._set_uniform(prog, "u_color_count", min(len(colors), 8))

        self._vao.render(moderngl.TRIANGLE_STRIP)

    def cleanup(self) -> None:
        if self._history_tex:
            self._history_tex.release()
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

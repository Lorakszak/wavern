"""Abstract base class for all visualization types."""

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams

logger = logging.getLogger(__name__)


class AbstractVisualization(ABC):
    """Base class for all visualization types.

    Subclasses implement the rendering logic for a specific visual style.
    Each visualization owns its own shader programs and GPU buffers,
    created during initialize() and released during cleanup().

    Lifecycle:
        1. __init__(ctx, params) — store references
        2. initialize() — create shaders, buffers, textures
        3. render(frame, fbo, resolution) — called every frame
        4. update_params(params) — called when user edits settings live
        5. cleanup() — release GPU resources
    """

    # Subclasses MUST override these
    NAME: ClassVar[str]
    DISPLAY_NAME: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    CATEGORY: ClassVar[str]  # "waveform", "spectrum", "particle", "abstract"

    # Tunable parameters: keys are param names, values are dicts with
    # "type", "default", "min", "max", "label", and optionally "choices".
    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]]

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        self.ctx = ctx
        self.params = params

    def get_param(self, name: str, default: Any = None) -> Any:
        """Get a parameter value, falling back to PARAM_SCHEMA default."""
        if name in self.params.params:
            return self.params.params[name]
        schema = self.PARAM_SCHEMA.get(name, {})
        return schema.get("default", default)

    @staticmethod
    def _set_uniform(prog: moderngl.Program, name: str, value: Any) -> None:
        """Set a uniform value safely, skipping if the uniform was optimized out."""
        if name in prog:
            prog[name].value = value

    @staticmethod
    def _write_uniform(prog: moderngl.Program, name: str, data: bytes) -> None:
        """Write raw bytes to a uniform safely, skipping if optimized out."""
        if name in prog:
            prog[name].write(data)

    @abstractmethod
    def initialize(self) -> None:
        """Create GPU resources (shader programs, VAOs, buffers, textures).

        Called once after construction and whenever the OpenGL context is recreated.
        """

    @abstractmethod
    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        """Render one frame of the visualization into the given framebuffer.

        Args:
            frame: Audio analysis data for the current moment in time.
            fbo: Target framebuffer (screen FBO for preview, offscreen FBO for export).
            resolution: (width, height) in pixels.
        """

    def update_params(self, params: VisualizationParams) -> None:
        """Update tunable parameters (called when user changes settings live).

        Default implementation stores the new params. Override if you
        need to rebuild GPU resources when params change.
        """
        self.params = params

    @abstractmethod
    def cleanup(self) -> None:
        """Release all GPU resources. Called before context destruction."""

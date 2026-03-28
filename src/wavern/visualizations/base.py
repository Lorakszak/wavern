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
            prog[name].value = value  # type: ignore[reportAttributeAccessIssue]

    @staticmethod
    def _write_uniform(prog: moderngl.Program, name: str, data: bytes) -> None:
        """Write raw bytes to a uniform safely, skipping if optimized out."""
        if name in prog:
            prog[name].write(data)  # type: ignore[reportAttributeAccessIssue]

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

    @property
    def program(self) -> moderngl.Program | None:
        """Return the compiled shader program, if any.

        Subclasses should set self._prog during initialize().
        Used by the renderer's shader cache.
        """
        return getattr(self, "_prog", None)

    def initialize_with_program(self, program: moderngl.Program) -> None:
        """Initialize using a pre-compiled shader program from cache.

        Skips shader compilation. Subclasses that need additional GPU resources
        beyond the main program should override and call super().
        """
        self._prog = program
        self._create_geometry()

    def _create_geometry(self) -> None:
        """Create vertex buffers and arrays using self._prog.

        Subclasses override this to create their specific geometry. Called
        by both initialize() (after compiling shaders) and
        initialize_with_program() (when using cached shaders).

        Default is a no-op — visualizations opt in to cache support
        by implementing this method.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Release all GPU resources. Called before context destruction."""

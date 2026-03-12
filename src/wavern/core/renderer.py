"""Render pipeline — orchestrates background, visualization, and post-processing."""

import logging
from pathlib import Path

import moderngl
import numpy as np
from numpy.typing import NDArray

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import Preset, BackgroundConfig
from wavern.utils.color import hex_to_rgb, hex_to_rgba
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


class Renderer:
    """Orchestrates the per-frame rendering pipeline.

    This class is the single rendering path used by BOTH the real-time GUI preview
    and the offline video export. The only difference is the target FBO.
    """

    def __init__(self, ctx: moderngl.Context) -> None:
        self.ctx = ctx
        self._visualization: AbstractVisualization | None = None
        self._preset: Preset | None = None
        self._offscreen_fbo: moderngl.Framebuffer | None = None
        self._offscreen_texture: moderngl.Texture | None = None
        self._bg_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def set_preset(self, preset: Preset) -> None:
        """Load a visualization from the registry and initialize it."""
        if self._visualization is not None:
            self._visualization.cleanup()
            self._visualization = None

        self._preset = preset

        # Resolve background color
        bg = preset.background
        if bg.type == "solid":
            self._bg_color = hex_to_rgba(bg.color)
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)
        else:
            self._bg_color = hex_to_rgba(bg.color)

        # Prepare color data for the visualization
        colors_rgb = [hex_to_rgb(c) for c in preset.color_palette]
        preset.visualization.params["_colors"] = colors_rgb
        if colors_rgb:
            preset.visualization.params["_primary_color"] = colors_rgb[0]

        # Instantiate visualization
        registry = VisualizationRegistry()
        viz_class = registry.get(preset.visualization.visualization_type)
        try:
            self._visualization = viz_class(self.ctx, preset.visualization)
            self._visualization.initialize()
            logger.info(
                "Loaded visualization: %s (%s)",
                viz_class.DISPLAY_NAME,
                viz_class.NAME,
            )
        except Exception as e:
            logger.error("Failed to initialize visualization %s: %s", viz_class.NAME, e)
            self._visualization = None

    def update_params(self, preset: Preset) -> None:
        """Update the current visualization's parameters without recreating it.

        If the visualization type changed, does a full reload via set_preset().
        """
        # Detect visualization type change → full reload needed
        current_type = (
            self._visualization.NAME
            if self._visualization is not None
            else None
        )
        if current_type != preset.visualization.visualization_type:
            self.set_preset(preset)
            return

        self._preset = preset

        colors_rgb = [hex_to_rgb(c) for c in preset.color_palette]
        preset.visualization.params["_colors"] = colors_rgb
        if colors_rgb:
            preset.visualization.params["_primary_color"] = colors_rgb[0]

        bg = preset.background
        if bg.type == "solid":
            self._bg_color = hex_to_rgba(bg.color)
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)

        if self._visualization is not None:
            self._visualization.update_params(preset.visualization)

    def render_frame(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        """Render a complete frame: background + visualization.

        Args:
            frame: Audio analysis data for this moment.
            fbo: Target framebuffer.
            resolution: (width, height) in pixels.
        """
        fbo.use()
        self.ctx.viewport = (0, 0, resolution[0], resolution[1])

        # Clear with background color (alpha=0 for transparent background)
        self.ctx.clear(
            self._bg_color[0],
            self._bg_color[1],
            self._bg_color[2],
            self._bg_color[3],
        )

        # Enable blending for transparent compositing
        if self._bg_color[3] < 1.0:
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = (
                moderngl.SRC_ALPHA,
                moderngl.ONE_MINUS_SRC_ALPHA,
            )

        # Render visualization
        if self._visualization is not None:
            try:
                self._visualization.render(frame, fbo, resolution)
            except Exception as e:
                logger.error("Visualization render error: %s", e)

    def read_pixels(
        self,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
        components: int = 3,
    ) -> NDArray[np.uint8]:
        """Read rendered pixels from FBO as numpy array.

        Args:
            fbo: Framebuffer to read from.
            resolution: (width, height) in pixels.
            components: 3 for RGB, 4 for RGBA (transparent export).

        Returns:
            Array of shape (H, W, components) with dtype uint8.
        """
        fbo.use()
        data = fbo.read(components=components)
        arr = np.frombuffer(data, dtype=np.uint8).reshape(
            resolution[1], resolution[0], components
        )
        # Flip vertically (OpenGL has origin at bottom-left)
        return np.flipud(arr).copy()

    def ensure_offscreen_fbo(
        self, resolution: tuple[int, int]
    ) -> moderngl.Framebuffer:
        """Create or resize the offscreen FBO for export rendering."""
        if self._offscreen_fbo is not None:
            if (
                self._offscreen_texture is not None
                and self._offscreen_texture.size == resolution
            ):
                return self._offscreen_fbo
            self._offscreen_texture.release()
            self._offscreen_fbo.release()

        self._offscreen_texture = self.ctx.texture(resolution, 4)
        self._offscreen_fbo = self.ctx.framebuffer(
            color_attachments=[self._offscreen_texture]
        )
        return self._offscreen_fbo

    def cleanup(self) -> None:
        """Release all GPU resources."""
        if self._visualization is not None:
            self._visualization.cleanup()
            self._visualization = None
        if self._offscreen_fbo is not None:
            self._offscreen_fbo.release()
            self._offscreen_fbo = None
        if self._offscreen_texture is not None:
            self._offscreen_texture.release()
            self._offscreen_texture = None

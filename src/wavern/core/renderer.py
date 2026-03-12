"""Render pipeline — orchestrates background, visualization, and post-processing."""

import logging

import moderngl
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import BackgroundConfig, ColorStop, Preset
from wavern.shaders import load_shader
from wavern.utils.color import hex_to_rgb, hex_to_rgba
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)


def _gradient_to_rgba(stops: list[ColorStop], width: int = 256) -> NDArray[np.uint8]:
    """Generate a 1-row RGBA image by linearly interpolating gradient stops.

    Args:
        stops: List of ColorStop with position (0-1) and hex color.
        width: Pixel width of the output gradient.

    Returns:
        Array of shape (1, width, 4) with dtype uint8.
    """
    sorted_stops = sorted(stops, key=lambda s: s.position)
    if len(sorted_stops) < 2:
        sorted_stops = [
            ColorStop(position=0.0, color="#000000"),
            ColorStop(position=1.0, color="#FFFFFF"),
        ]

    result = np.zeros((1, width, 4), dtype=np.uint8)
    for x in range(width):
        t = x / max(width - 1, 1)
        # Find surrounding stops
        left = sorted_stops[0]
        right = sorted_stops[-1]
        for i in range(len(sorted_stops) - 1):
            if sorted_stops[i].position <= t <= sorted_stops[i + 1].position:
                left = sorted_stops[i]
                right = sorted_stops[i + 1]
                break

        span = right.position - left.position
        local_t = (t - left.position) / span if span > 0 else 0.0
        r1, g1, b1 = hex_to_rgb(left.color)
        r2, g2, b2 = hex_to_rgb(right.color)
        result[0, x] = [
            int((r1 + (r2 - r1) * local_t) * 255),
            int((g1 + (g2 - g1) * local_t) * 255),
            int((b1 + (b2 - b1) * local_t) * 255),
            255,
        ]
    return result


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

        # Background quad rendering resources (created lazily)
        self._bg_program: moderngl.Program | None = None
        self._bg_vao: moderngl.VertexArray | None = None
        self._bg_texture: moderngl.Texture | None = None
        self._bg_image_path: str | None = None  # tracks loaded image to avoid reloading

    def _ensure_bg_quad(self) -> None:
        """Lazily create the fullscreen quad shader and VAO for background rendering."""
        if self._bg_program is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("background.frag")
        self._bg_program = self.ctx.program(
            vertex_shader=vert_src, fragment_shader=frag_src
        )

        # Fullscreen quad: two triangles, positions + texcoords
        vertices = np.array(
            [
                # x,    y,   u,   v
                -1.0, -1.0, 0.0, 0.0,
                 1.0, -1.0, 1.0, 0.0,
                -1.0,  1.0, 0.0, 1.0,
                 1.0,  1.0, 1.0, 1.0,
            ],
            dtype="f4",
        )
        vbo = self.ctx.buffer(vertices.tobytes())
        self._bg_vao = self.ctx.vertex_array(
            self._bg_program,
            [(vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _release_bg_texture(self) -> None:
        """Release the current background texture if any."""
        if self._bg_texture is not None:
            self._bg_texture.release()
            self._bg_texture = None
        self._bg_image_path = None

    def _update_bg_texture(self, bg: BackgroundConfig) -> None:
        """Create or update the background texture based on config."""
        if bg.type == "gradient":
            self._release_bg_texture()
            data = _gradient_to_rgba(bg.gradient_stops)
            self._bg_texture = self.ctx.texture((data.shape[1], data.shape[0]), 4, data.tobytes())
            self._bg_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        elif bg.type == "image":
            if bg.image_path and bg.image_path != self._bg_image_path:
                self._release_bg_texture()
                try:
                    img = Image.open(bg.image_path).convert("RGBA")
                    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    self._bg_texture = self.ctx.texture(img.size, 4, img.tobytes())
                    self._bg_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    self._bg_image_path = bg.image_path
                except Exception as e:
                    logger.error("Failed to load background image %s: %s", bg.image_path, e)
                    self._bg_texture = None
            elif not bg.image_path:
                self._release_bg_texture()
        else:
            self._release_bg_texture()

    def _render_bg_quad(self, fbo: moderngl.Framebuffer) -> None:
        """Render the background texture as a fullscreen quad."""
        if self._bg_texture is None or self._bg_vao is None:
            return
        self._bg_texture.use(location=0)
        self._bg_program["u_background"].value = 0
        self._bg_vao.render(moderngl.TRIANGLE_STRIP)

    def set_preset(self, preset: Preset) -> None:
        """Load a visualization from the registry and initialize it."""
        if self._visualization is not None:
            self._visualization.cleanup()
            self._visualization = None

        self._preset = preset

        # Resolve background
        bg = preset.background
        if bg.type == "solid":
            self._bg_color = hex_to_rgba(bg.color)
            self._release_bg_texture()
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)
            self._release_bg_texture()
        elif bg.type in ("gradient", "image"):
            self._bg_color = (0.0, 0.0, 0.0, 1.0)
            self._ensure_bg_quad()
            self._update_bg_texture(bg)
        else:
            self._bg_color = hex_to_rgba(bg.color)
            self._release_bg_texture()

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
            self._release_bg_texture()
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)
            self._release_bg_texture()
        elif bg.type in ("gradient", "image"):
            self._bg_color = (0.0, 0.0, 0.0, 1.0)
            self._ensure_bg_quad()
            self._update_bg_texture(bg)

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

        # Render gradient/image background quad
        if self._bg_texture is not None:
            self._render_bg_quad(fbo)

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
        self._release_bg_texture()
        if self._bg_vao is not None:
            self._bg_vao.release()
            self._bg_vao = None
        if self._bg_program is not None:
            self._bg_program.release()
            self._bg_program = None

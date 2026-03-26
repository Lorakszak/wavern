"""Render pipeline — orchestrates background, visualization, and post-processing."""

import logging
import math
import struct

import moderngl
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.text_overlay import TextOverlay
from wavern.core.video_source import VideoSource
from wavern.presets.schema import (
    BackgroundConfig,
    BackgroundMovement,
    BlendMode,
    ColorStop,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
    VisualizationLayer,
    VisualizationParams,
)
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

    # Movement type name → integer mapping for the shader uniform
    _MOVEMENT_TYPE_MAP: dict[str, int] = {
        "none": 0, "drift": 1, "shake": 2,
        "wave": 3, "zoom_pulse": 4, "breathe": 5,
    }

    def __init__(self, ctx: moderngl.Context) -> None:
        self.ctx = ctx
        self._layers: list[tuple[VisualizationLayer, AbstractVisualization | None]] = []
        self._layer_fbos: list[moderngl.Framebuffer] = []
        self._layer_textures: list[moderngl.Texture] = []
        self._composite_prog: moderngl.Program | None = None
        self._composite_vao: moderngl.VertexArray | None = None
        self._composite_vbo: moderngl.Buffer | None = None
        self._layer_fbo_resolution: tuple[int, int] | None = None
        self._preset: Preset | None = None
        self._offscreen_fbo: moderngl.Framebuffer | None = None
        self._offscreen_texture: moderngl.Texture | None = None
        self._bg_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

        # Background quad rendering resources (created lazily)
        self._bg_program: moderngl.Program | None = None
        self._bg_vbo: moderngl.Buffer | None = None
        self._bg_vao: moderngl.VertexArray | None = None
        self._bg_texture: moderngl.Texture | None = None
        self._bg_image_path: str | None = None  # tracks loaded image to avoid reloading

        # Background video source
        self._video_source: VideoSource | None = None
        self._bg_video_path: str | None = None

        # Video overlay resources
        self._overlay_video_source: VideoSource | None = None
        self._overlay_texture: moderngl.Texture | None = None
        self._overlay_program: moderngl.Program | None = None
        self._overlay_vbo: moderngl.Buffer | None = None
        self._overlay_vao: moderngl.VertexArray | None = None
        self._overlay_video_path: str | None = None

        # Text overlay (created lazily)
        self._text_overlay: TextOverlay | None = None

        # Preview-mode flags: when True, the layer is skipped during preview
        # but still rendered during export.
        self.skip_bg_preview: bool = False
        self.skip_overlay_preview: bool = False

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
        self._bg_vbo = self.ctx.buffer(vertices.tobytes())
        self._bg_vao = self.ctx.vertex_array(
            self._bg_program,
            [(self._bg_vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _release_bg_texture(self) -> None:
        """Release the current background texture if any."""
        if self._bg_texture is not None:
            self._bg_texture.release()
            self._bg_texture = None
        self._bg_image_path = None

    def _close_video_source(self) -> None:
        """Close the background video source if open."""
        if self._video_source is not None:
            self._video_source.close()
            self._video_source = None
        self._bg_video_path = None

    def _update_bg_texture(self, bg: BackgroundConfig) -> None:
        """Create or update the background texture based on config."""
        logger.debug(
            "Updating bg texture: type=%s, image_path=%s, video_path=%s",
            bg.type, bg.image_path, bg.video_path,
        )
        if bg.type == "gradient":
            self._release_bg_texture()
            self._close_video_source()
            data = _gradient_to_rgba(bg.gradient_stops)
            self._bg_texture = self.ctx.texture((data.shape[1], data.shape[0]), 4, data.tobytes())
            self._bg_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        elif bg.type == "image":
            self._close_video_source()
            if bg.image_path and bg.image_path != self._bg_image_path:
                self._release_bg_texture()
                try:
                    img = Image.open(bg.image_path).convert("RGBA")
                    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    self._bg_texture = self.ctx.texture(img.size, 4, img.tobytes())
                    self._bg_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    self._bg_image_path = bg.image_path
                    logger.debug(
                        "Loaded bg image: %s, texture size=%s",
                        bg.image_path, self._bg_texture.size,
                    )
                except Exception as e:
                    logger.error("Failed to load background image %s: %s", bg.image_path, e)
                    self._bg_texture = None
            elif not bg.image_path:
                logger.debug("No image_path set — releasing bg texture")
                self._release_bg_texture()

        elif bg.type == "video":
            if bg.video_path and bg.video_path != self._bg_video_path:
                self._release_bg_texture()
                self._close_video_source()
                try:
                    vs = VideoSource(bg.video_path)
                    vs.open()
                    w, h = vs.size
                    # Create RGBA texture at video dimensions — data uploaded per-frame
                    self._bg_texture = self.ctx.texture((w, h), 4)
                    self._bg_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    self._video_source = vs
                    self._bg_video_path = bg.video_path
                except Exception as e:
                    logger.error("Failed to open background video %s: %s", bg.video_path, e)
                    self._bg_texture = None
            elif not bg.video_path:
                self._release_bg_texture()
                self._close_video_source()
        else:
            self._release_bg_texture()
            self._close_video_source()

    def _set_bg_movement_uniforms(self, movement: BackgroundMovement, timestamp: float) -> None:
        """Upload movement uniforms to the background shader program."""
        prog = self._bg_program
        if prog is None:
            return
        mv_type = self._MOVEMENT_TYPE_MAP.get(movement.type, 0)
        if "u_time" in prog:
            prog["u_time"].value = timestamp  # type: ignore[reportAttributeAccessIssue]
        if "u_movement_type" in prog:
            prog["u_movement_type"].value = mv_type  # type: ignore[reportAttributeAccessIssue]
        if "u_movement_speed" in prog:
            prog["u_movement_speed"].value = movement.speed  # type: ignore[reportAttributeAccessIssue]
        if "u_movement_intensity" in prog:
            prog["u_movement_intensity"].value = movement.intensity  # type: ignore[reportAttributeAccessIssue]
        if "u_movement_angle" in prog:
            prog["u_movement_angle"].value = math.radians(movement.angle)  # type: ignore[reportAttributeAccessIssue]
        if "u_clamp_to_frame" in prog:
            prog["u_clamp_to_frame"].value = int(movement.clamp_to_frame)  # type: ignore[reportAttributeAccessIssue]

    def _render_bg_quad(self, fbo: moderngl.Framebuffer, frame: FrameAnalysis) -> None:
        """Render the background texture as a fullscreen quad."""
        if self._bg_texture is None or self._bg_vao is None:
            return

        # Upload video frame if using video background
        if self._video_source is not None:
            frame_data = self._video_source.get_frame(frame.timestamp)
            self._bg_texture.write(frame_data.tobytes())

        self._bg_texture.use(location=0)
        self._bg_program["u_background"].value = 0  # type: ignore[reportAttributeAccessIssue]

        # Set transform and movement uniforms
        if self._preset is not None:
            bg = self._preset.background
            movement = bg.movement
            self._set_bg_movement_uniforms(movement, frame.timestamp)

            # Transform uniforms (rotation, mirror)
            if "u_rotation" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_rotation"].value = math.radians(bg.rotation)  # type: ignore[reportAttributeAccessIssue]
            if "u_mirror_x" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_mirror_x"].value = int(bg.mirror_x)  # type: ignore[reportAttributeAccessIssue]
            if "u_mirror_y" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_mirror_y"].value = int(bg.mirror_y)  # type: ignore[reportAttributeAccessIssue]

            # Enable texture repeat for drift (when not clamped)
            if movement.type == "drift" and self._bg_texture is not None:
                self._bg_texture.repeat_x = True
                self._bg_texture.repeat_y = True

        self._bg_vao.render(moderngl.TRIANGLE_STRIP)

    def _ensure_layer_fbos(self, resolution: tuple[int, int]) -> None:
        """Create or resize layer FBOs to match resolution."""
        if (
            self._layer_fbo_resolution == resolution
            and len(self._layer_fbos) == len(self._layers)
        ):
            return
        self._release_layer_fbos()
        for _ in self._layers:
            tex = self.ctx.texture(resolution, 4)
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            layer_fbo = self.ctx.framebuffer(color_attachments=[tex])
            self._layer_textures.append(tex)
            self._layer_fbos.append(layer_fbo)
        self._layer_fbo_resolution = resolution
        logger.debug("Created %d layer FBOs at %dx%d", len(self._layer_fbos), *resolution)

    def _release_layer_fbos(self) -> None:
        """Release all layer FBOs and textures."""
        for layer_fbo in self._layer_fbos:
            layer_fbo.release()
        for tex in self._layer_textures:
            tex.release()
        self._layer_fbos.clear()
        self._layer_textures.clear()
        self._layer_fbo_resolution = None

    def _ensure_composite_shader(self) -> None:
        """Lazily create the compositing shader and fullscreen quad."""
        if self._composite_prog is not None:
            return
        vert_src = load_shader("composite.vert")
        frag_src = load_shader("composite.frag")
        self._composite_prog = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )
        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,
             1.0, -1.0, 1.0, 0.0,
            -1.0,  1.0, 0.0, 1.0,
             1.0,  1.0, 1.0, 1.0,
        ], dtype="f4")
        self._composite_vbo = self.ctx.buffer(vertices.tobytes())
        self._composite_vao = self.ctx.vertex_array(
            self._composite_prog,
            [(self._composite_vbo, "2f 2f", "in_position", "in_uv")],
        )

    def set_preset(self, preset: Preset) -> None:
        """Load visualization layers from the registry and initialize them."""
        # Clean up old layers
        for _, viz in self._layers:
            if viz is not None:
                viz.cleanup()
        self._layers.clear()

        self._preset = preset

        # Resolve background
        bg = preset.background
        if bg.type == "solid":
            self._bg_color = hex_to_rgba(bg.color)
            self._release_bg_texture()
            self._close_video_source()
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)
            self._release_bg_texture()
            self._close_video_source()
        elif bg.type in ("gradient", "image", "video"):
            self._bg_color = (0.0, 0.0, 0.0, 1.0)
            self._ensure_bg_quad()
            self._update_bg_texture(bg)
        else:
            self._bg_color = hex_to_rgba(bg.color)
            self._release_bg_texture()
            self._close_video_source()

        # Update video overlay
        self._update_overlay(preset.video_overlay)

        # Update text overlay config
        self._ensure_text_overlay()
        assert self._text_overlay is not None
        self._text_overlay.update_config(preset.overlay)

        # Instantiate visualization layers
        registry = VisualizationRegistry()
        for layer_cfg in preset.layers:
            colors = layer_cfg.colors
            colors_rgb = [hex_to_rgb(c) for c in colors]

            viz_params = VisualizationParams(
                visualization_type=layer_cfg.visualization_type,
                params=dict(layer_cfg.params),
            )
            viz_params.params["_colors"] = colors_rgb
            if colors_rgb:
                viz_params.params["_primary_color"] = colors_rgb[0]

            try:
                viz_class = registry.get(layer_cfg.visualization_type)
                viz = viz_class(self.ctx, viz_params)
                viz.initialize()
                self._layers.append((layer_cfg, viz))
                logger.info("Loaded layer: %s (%s)", viz_class.DISPLAY_NAME, viz_class.NAME)
            except Exception as e:
                logger.warning("Skipping layer '%s': %s", layer_cfg.visualization_type, e)
                self._layers.append((layer_cfg, None))

    def update_params(self, preset: Preset) -> None:
        """Update parameters without recreating unless layer structure changed."""
        # Detect structural change → full reload
        if len(preset.layers) != len(self._layers):
            self.set_preset(preset)
            return
        for i, (old_cfg, _) in enumerate(self._layers):
            if old_cfg.visualization_type != preset.layers[i].visualization_type:
                self.set_preset(preset)
                return

        self._preset = preset

        bg = preset.background
        if bg.type == "solid":
            self._bg_color = hex_to_rgba(bg.color)
            self._release_bg_texture()
            self._close_video_source()
        elif bg.type == "none":
            self._bg_color = (0.0, 0.0, 0.0, 0.0)
            self._release_bg_texture()
            self._close_video_source()
        elif bg.type in ("gradient", "image", "video"):
            self._bg_color = (0.0, 0.0, 0.0, 1.0)
            self._ensure_bg_quad()
            self._update_bg_texture(bg)

        # Update video overlay
        self._update_overlay(preset.video_overlay)

        # Update text overlay config
        self._ensure_text_overlay()
        assert self._text_overlay is not None
        self._text_overlay.update_config(preset.overlay)

        # Update each layer's params
        for i, (_, viz) in enumerate(self._layers):
            layer_cfg = preset.layers[i]
            colors = layer_cfg.colors
            colors_rgb = [hex_to_rgb(c) for c in colors]

            viz_params = VisualizationParams(
                visualization_type=layer_cfg.visualization_type,
                params=dict(layer_cfg.params),
            )
            viz_params.params["_colors"] = colors_rgb
            if colors_rgb:
                viz_params.params["_primary_color"] = colors_rgb[0]

            if viz is not None:
                viz.update_params(viz_params)

            # Update stored layer config
            self._layers[i] = (layer_cfg, viz)

    def set_duration(self, total_seconds: float) -> None:
        """Set total audio duration for countdown overlay."""
        self._ensure_text_overlay()
        assert self._text_overlay is not None
        self._text_overlay.set_duration(total_seconds)

    def _ensure_text_overlay(self) -> None:
        """Lazily create the text overlay renderer."""
        if self._text_overlay is None:
            self._text_overlay = TextOverlay(self.ctx)

    def render_frame(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
        preview: bool = False,
    ) -> None:
        """Render a complete frame: background + visualization.

        Args:
            frame: Audio analysis data for this moment.
            fbo: Target framebuffer.
            resolution: (width, height) in pixels.
            preview: True when rendering for GUI preview. When True,
                layers with their preview-skip flag set are not drawn.
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

        # Render gradient/image/video background quad
        skip_bg = preview and self.skip_bg_preview
        if self._bg_texture is not None and not skip_bg:
            self._render_bg_quad(fbo, frame)

        # Multi-layer rendering: each layer to its own FBO, then composite
        self._ensure_layer_fbos(resolution)
        self._ensure_composite_shader()

        # Disable blending for individual layer renders — each layer renders
        # to its own transparent FBO. Blending on would corrupt alpha.
        self.ctx.disable(moderngl.BLEND)

        visible_layer_indices: list[int] = []
        for i, (layer_cfg, viz) in enumerate(self._layers):
            if not layer_cfg.visible or viz is None:
                continue

            self._layer_fbos[i].use()
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            self.ctx.viewport = (0, 0, resolution[0], resolution[1])

            try:
                viz.render(frame, self._layer_fbos[i], resolution)
            except Exception as e:
                logger.error("Layer %d render error: %s", i, e)
                continue

            visible_layer_indices.append(i)

        # Re-enable blending for compositing pass (alpha-over onto background)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

        # Compositing pass — blend all layers onto final FBO
        if visible_layer_indices and self._composite_prog is not None and self._composite_vao is not None:
            fbo.use()
            self.ctx.viewport = (0, 0, resolution[0], resolution[1])

            blend_mode_map = {
                BlendMode.NORMAL: 0,
                BlendMode.ADDITIVE: 1,
                BlendMode.SCREEN: 2,
                BlendMode.MULTIPLY: 3,
            }

            # Bind layer textures to sequential texture units
            for i in range(len(self._layers)):
                self._layer_textures[i].use(location=i)

            # Upload uniform arrays as packed data
            n = len(self._layers)
            sampler_values = list(range(7))
            opacities = [self._layers[i][0].opacity if i < n else 0.0 for i in range(7)]
            blend_modes = [
                blend_mode_map.get(self._layers[i][0].blend_mode, 0) if i < n else 0
                for i in range(7)
            ]
            visible = [
                (1 if self._layers[i][0].visible and self._layers[i][1] is not None else 0)
                if i < n else 0
                for i in range(7)
            ]

            self._composite_prog["u_layer_count"].value = n  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_layers"].write(struct.pack("7i", *sampler_values))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_opacities"].write(struct.pack("7f", *opacities))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_blend_modes"].write(struct.pack("7i", *blend_modes))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_visible"].write(struct.pack("7i", *visible))  # type: ignore[reportAttributeAccessIssue]

            self._composite_vao.render(moderngl.TRIANGLE_STRIP)

        # Render video overlay on top of visualization
        skip_overlay = preview and self.skip_overlay_preview
        if self._overlay_video_source is not None and not skip_overlay:
            try:
                self._render_overlay(frame)
            except Exception as e:
                logger.error("Video overlay render error: %s", e)

        # Render text overlay on top
        if self._text_overlay is not None:
            try:
                self._text_overlay.render(fbo, resolution, frame.timestamp)
            except Exception as e:
                logger.error("Text overlay render error: %s", e)

    def _ensure_overlay_quad(self) -> None:
        """Lazily create the overlay fullscreen quad shader and VAO."""
        if self._overlay_program is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("overlay.frag")
        self._overlay_program = self.ctx.program(
            vertex_shader=vert_src, fragment_shader=frag_src,
        )

        vertices = np.array(
            [
                -1.0, -1.0, 0.0, 0.0,
                 1.0, -1.0, 1.0, 0.0,
                -1.0,  1.0, 0.0, 1.0,
                 1.0,  1.0, 1.0, 1.0,
            ],
            dtype="f4",
        )
        self._overlay_vbo = self.ctx.buffer(vertices.tobytes())
        self._overlay_vao = self.ctx.vertex_array(
            self._overlay_program,
            [(self._overlay_vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _update_overlay(self, config: VideoOverlayConfig) -> None:
        """Open/close the overlay video source based on config."""
        if not config.enabled or not config.video_path:
            self._close_overlay()
            return

        if config.video_path != self._overlay_video_path:
            self._close_overlay()
            try:
                vs = VideoSource(config.video_path)
                vs.open()
                w, h = vs.size
                self._ensure_overlay_quad()
                self._overlay_texture = self.ctx.texture((w, h), 4)
                self._overlay_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                self._overlay_video_source = vs
                self._overlay_video_path = config.video_path
            except Exception as e:
                logger.error("Failed to open overlay video %s: %s", config.video_path, e)

    def _close_overlay(self) -> None:
        """Release overlay video source and texture."""
        if self._overlay_video_source is not None:
            self._overlay_video_source.close()
            self._overlay_video_source = None
        if self._overlay_texture is not None:
            self._overlay_texture.release()
            self._overlay_texture = None
        self._overlay_video_path = None

    def _render_overlay(self, frame: FrameAnalysis) -> None:
        """Decode and composite the video overlay on top of the current scene."""
        if (
            self._overlay_video_source is None
            or self._overlay_texture is None
            or self._overlay_program is None
            or self._overlay_vao is None
            or self._preset is None
        ):
            return

        overlay_cfg = self._preset.video_overlay
        frame_data = self._overlay_video_source.get_frame(frame.timestamp)
        self._overlay_texture.write(frame_data.tobytes())
        self._overlay_texture.use(location=0)
        self._overlay_program["u_overlay"].value = 0  # type: ignore[reportAttributeAccessIssue]

        if "u_opacity" in self._overlay_program:
            self._overlay_program["u_opacity"].value = overlay_cfg.opacity  # type: ignore[reportAttributeAccessIssue]
        if "u_rotation" in self._overlay_program:
            self._overlay_program["u_rotation"].value = math.radians(overlay_cfg.rotation)  # type: ignore[reportAttributeAccessIssue]
        if "u_mirror_x" in self._overlay_program:
            self._overlay_program["u_mirror_x"].value = int(overlay_cfg.mirror_x)  # type: ignore[reportAttributeAccessIssue]
        if "u_mirror_y" in self._overlay_program:
            self._overlay_program["u_mirror_y"].value = int(overlay_cfg.mirror_y)  # type: ignore[reportAttributeAccessIssue]

        # Set blend mode
        self.ctx.enable(moderngl.BLEND)
        if overlay_cfg.blend_mode == OverlayBlendMode.ALPHA:
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        elif overlay_cfg.blend_mode == OverlayBlendMode.ADDITIVE:
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
        elif overlay_cfg.blend_mode == OverlayBlendMode.SCREEN:
            self.ctx.blend_func = (moderngl.ONE, moderngl.ONE_MINUS_SRC_COLOR)

        self._overlay_vao.render(moderngl.TRIANGLE_STRIP)

        # Restore default blend state
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

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
            self._offscreen_fbo.release()
            if self._offscreen_texture is not None:
                self._offscreen_texture.release()

        self._offscreen_texture = self.ctx.texture(resolution, 4)
        self._offscreen_fbo = self.ctx.framebuffer(
            color_attachments=[self._offscreen_texture]
        )
        logger.debug("Created offscreen FBO: %dx%d", resolution[0], resolution[1])
        return self._offscreen_fbo

    def cleanup(self) -> None:
        """Release all GPU resources."""
        if self._text_overlay is not None:
            self._text_overlay.cleanup()
            self._text_overlay = None
        for _, viz in self._layers:
            if viz is not None:
                viz.cleanup()
        self._layers.clear()
        self._release_layer_fbos()
        if self._composite_vao is not None:
            self._composite_vao.release()
            self._composite_vao = None
        if self._composite_vbo is not None:
            self._composite_vbo.release()
            self._composite_vbo = None
        if self._composite_prog is not None:
            self._composite_prog.release()
            self._composite_prog = None
        if self._offscreen_fbo is not None:
            self._offscreen_fbo.release()
            self._offscreen_fbo = None
        if self._offscreen_texture is not None:
            self._offscreen_texture.release()
            self._offscreen_texture = None
        self._release_bg_texture()
        self._close_video_source()
        self._close_overlay()
        if self._bg_vao is not None:
            self._bg_vao.release()
            self._bg_vao = None
        if self._bg_vbo is not None:
            self._bg_vbo.release()
            self._bg_vbo = None
        if self._bg_program is not None:
            self._bg_program.release()
            self._bg_program = None
        if self._overlay_vao is not None:
            self._overlay_vao.release()
            self._overlay_vao = None
        if self._overlay_vbo is not None:
            self._overlay_vbo.release()
            self._overlay_vbo = None
        if self._overlay_program is not None:
            self._overlay_program.release()
            self._overlay_program = None

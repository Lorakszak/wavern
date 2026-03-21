"""Text overlay renderer — draws title and countdown on top of visualizations."""

import logging

import moderngl
import numpy as np
from PIL import Image, ImageDraw

from wavern.core.font_manager import get_font, list_available_fonts
from wavern.presets.schema import OverlayConfig
from wavern.shaders import load_shader
from wavern.utils.color import hex_to_rgb

logger = logging.getLogger(__name__)

# Countdown format display labels (for settings panel)
COUNTDOWN_FORMATS = {
    "elapsed_total": "Elapsed / Total",
    "remaining": "Remaining",
    "elapsed": "Elapsed",
}

# Re-export for settings panel convenience
AVAILABLE_FONTS = list_available_fonts


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    total = int(max(0, seconds))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


class TextOverlay:
    """Renders title and countdown text as a texture overlay.

    Uses PIL to render text onto an RGBA image, uploads it as a moderngl
    texture, and draws a fullscreen quad with alpha blending.

    Supports:
    - Configurable font family (auto-downloaded from Google Fonts)
    - Bold weight
    - Text outline/stroke (via PIL stroke_width)
    - Drop shadow (rendered as offset text behind main text)
    """

    def __init__(self, ctx: moderngl.Context) -> None:
        self.ctx = ctx
        self._config = OverlayConfig()
        self._total_duration: float = 0.0

        # GPU resources (created lazily)
        self._program: moderngl.Program | None = None
        self._vbo: moderngl.Buffer | None = None
        self._vao: moderngl.VertexArray | None = None
        self._texture: moderngl.Texture | None = None

        # Cache key to avoid re-rendering every frame
        self._cached_key: tuple | None = None

    def _ensure_quad(self) -> None:
        """Lazily create the shader program and fullscreen quad VAO."""
        if self._program is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("background.frag")
        self._program = self.ctx.program(
            vertex_shader=vert_src, fragment_shader=frag_src,
        )

        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,
             1.0, -1.0, 1.0, 0.0,
            -1.0,  1.0, 0.0, 1.0,
             1.0,  1.0, 1.0, 1.0,
        ], dtype="f4")
        self._vbo = self.ctx.buffer(vertices.tobytes())
        self._vao = self.ctx.vertex_array(
            self._program,
            [(self._vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def update_config(self, config: OverlayConfig) -> None:
        """Update overlay configuration."""
        self._config = config
        self._cached_key = None  # force re-render

    def set_duration(self, total_seconds: float) -> None:
        """Set total audio duration for countdown formatting."""
        self._total_duration = total_seconds
        self._cached_key = None

    def render(
        self,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
        timestamp: float,
    ) -> None:
        """Render text overlay on top of the current framebuffer contents."""
        cfg = self._config
        if not cfg.title_enabled and not cfg.countdown_enabled:
            return

        self._ensure_quad()

        # Build cache key — only re-render when text changes (once per second)
        text_key = (
            resolution,
            int(timestamp),
            cfg.title_enabled,
            cfg.title_text,
            cfg.countdown_enabled,
            cfg.countdown_format,
            cfg.link_positions,
            cfg.title_x, cfg.title_y,
            cfg.countdown_x, cfg.countdown_y,
            cfg.font_family, cfg.font_bold,
            cfg.font_size, cfg.font_color, cfg.font_opacity,
            cfg.outline_enabled, cfg.outline_color, cfg.outline_width,
            cfg.shadow_enabled, cfg.shadow_color, cfg.shadow_opacity,
            cfg.shadow_offset_x, cfg.shadow_offset_y,
            int(self._total_duration),
        )

        if text_key != self._cached_key:
            img = self._render_text_image(resolution, timestamp)
            if img is None:
                return
            self._upload_texture(img, resolution)
            self._cached_key = text_key

        if self._texture is None:
            return

        # Draw the text quad with alpha blending
        fbo.use()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self._texture.use(location=0)
        self._program["u_background"].value = 0
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def _render_text_image(
        self,
        resolution: tuple[int, int],
        timestamp: float,
    ) -> Image.Image | None:
        """Render overlay text to a PIL RGBA image."""
        cfg = self._config
        w, h = resolution

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = get_font(cfg.font_family, cfg.font_size, cfg.font_bold)

        # Main text color
        r, g, b = hex_to_rgb(cfg.font_color)
        ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
        alpha = int(cfg.font_opacity * 255)
        color = (ri, gi, bi, alpha)

        # Outline params
        stroke_width = cfg.outline_width if cfg.outline_enabled else 0
        stroke_fill: tuple[int, int, int, int] | None = None
        if cfg.outline_enabled:
            or_, og, ob = hex_to_rgb(cfg.outline_color)
            stroke_fill = (int(or_ * 255), int(og * 255), int(ob * 255), alpha)

        # Shadow params
        shadow_color: tuple[int, int, int, int] | None = None
        if cfg.shadow_enabled:
            sr, sg, sb = hex_to_rgb(cfg.shadow_color)
            sa = int(cfg.shadow_opacity * cfg.font_opacity * 255)
            shadow_color = (int(sr * 255), int(sg * 255), int(sb * 255), sa)

        title_str = cfg.title_text if cfg.title_enabled else ""
        countdown_str = self._format_countdown(timestamp) if cfg.countdown_enabled else ""

        if not title_str and not countdown_str:
            return None

        if cfg.link_positions:
            # Combined on one line
            parts = []
            if title_str:
                parts.append(title_str)
            if countdown_str:
                parts.append(countdown_str)
            combined = "  ".join(parts)

            px = int(cfg.title_x * w)
            # Y: 0.0 = bottom, 1.0 = top; PIL Y origin is top
            py = int((1.0 - cfg.title_y) * h)
            self._draw_styled_text(
                draw, (px, py), combined, font, color,
                stroke_width, stroke_fill, shadow_color, cfg,
            )
        else:
            # Independent positions
            if title_str:
                px = int(cfg.title_x * w)
                py = int((1.0 - cfg.title_y) * h)
                self._draw_styled_text(
                    draw, (px, py), title_str, font, color,
                    stroke_width, stroke_fill, shadow_color, cfg,
                )
            if countdown_str:
                px = int(cfg.countdown_x * w)
                py = int((1.0 - cfg.countdown_y) * h)
                self._draw_styled_text(
                    draw, (px, py), countdown_str, font, color,
                    stroke_width, stroke_fill, shadow_color, cfg,
                )

        return img

    @staticmethod
    def _draw_styled_text(
        draw: ImageDraw.ImageDraw,
        pos: tuple[int, int],
        text: str,
        font: object,
        color: tuple[int, int, int, int],
        stroke_width: int,
        stroke_fill: tuple[int, int, int, int] | None,
        shadow_color: tuple[int, int, int, int] | None,
        cfg: OverlayConfig,
    ) -> None:
        """Draw text with optional shadow and outline.

        Shadow is rendered first (behind), then main text with optional stroke
        on top. This layering gives the cinematic look.
        """
        # Shadow pass — offset text behind main
        if shadow_color is not None:
            sx = pos[0] + cfg.shadow_offset_x
            sy = pos[1] + cfg.shadow_offset_y
            draw.text(
                (sx, sy), text, fill=shadow_color, font=font, anchor="mm",
            )

        # Main text pass with optional outline
        draw.text(
            pos, text, fill=color, font=font, anchor="mm",
            stroke_width=stroke_width, stroke_fill=stroke_fill,
        )

    def _format_countdown(self, elapsed: float) -> str:
        """Format the countdown string according to the configured format."""
        fmt = self._config.countdown_format
        if fmt == "elapsed_total":
            return f"{_format_time(elapsed)} / {_format_time(self._total_duration)}"
        elif fmt == "remaining":
            remaining = max(0, self._total_duration - elapsed)
            return f"-{_format_time(remaining)}"
        else:  # "elapsed"
            return _format_time(elapsed)

    def _upload_texture(self, img: Image.Image, resolution: tuple[int, int]) -> None:
        """Upload a PIL image as a moderngl texture, replacing any existing one."""
        if self._texture is not None:
            if self._texture.size != resolution:
                self._texture.release()
                self._texture = None

        # Flip vertically for OpenGL
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        data = img.tobytes()

        if self._texture is None:
            self._texture = self.ctx.texture(resolution, 4, data)
            self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        else:
            self._texture.write(data)

    def cleanup(self) -> None:
        """Release all GPU resources."""
        if self._texture is not None:
            self._texture.release()
            self._texture = None
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._vbo is not None:
            self._vbo.release()
            self._vbo = None
        if self._program is not None:
            self._program.release()
            self._program = None

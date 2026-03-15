"""Shared image texture mixin for visualizations with inner image support."""

import logging
import math

import moderngl
from PIL import Image

logger = logging.getLogger(__name__)


class ImageTextureMixin:
    """Mixin providing inner image texture loading, caching, and beat-bounce logic."""

    _image_texture: moderngl.Texture | None
    _image_path_loaded: str
    _bounce_value: float
    _bounce_prev_time: float
    _fallback_texture: moderngl.Texture | None

    def _init_image_state(self) -> None:
        self._image_texture = None
        self._image_path_loaded = ""
        self._bounce_value = 0.0
        self._bounce_prev_time = 0.0
        self._fallback_texture = None

    def _ensure_fallback_texture(self, ctx: moderngl.Context) -> None:
        """Create a 1x1 transparent texture for when no image is loaded."""
        if self._fallback_texture is None:
            self._fallback_texture = ctx.texture((1, 1), 4, b'\x00\x00\x00\x00')

    def _update_image_texture(self, ctx: moderngl.Context, path: str) -> None:
        """Load or replace image texture. Caches by path."""
        if path == self._image_path_loaded:
            return
        self._release_image_texture()
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self._image_texture = ctx.texture(img.size, 4, img.tobytes())
            self._image_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._image_path_loaded = path
        except Exception:
            logger.error("Failed to load inner image: %s", path)

    def _release_image_texture(self) -> None:
        if self._image_texture is not None:
            self._image_texture.release()
            self._image_texture = None
        self._image_path_loaded = ""

    def _release_fallback_texture(self) -> None:
        if self._fallback_texture is not None:
            self._fallback_texture.release()
            self._fallback_texture = None

    def _compute_bounce(self, beat: bool, beat_intensity: float, timestamp: float) -> float:
        """Framerate-aware exponential decay bounce with graduated intensity."""
        dt = timestamp - self._bounce_prev_time
        if dt <= 0 or dt > 0.5:
            dt = 1.0 / 60.0
        self._bounce_prev_time = timestamp

        self._bounce_value *= math.exp(-dt / 0.15)
        if beat:
            self._bounce_value = max(self._bounce_value, beat_intensity)
        return self._bounce_value

    def _bind_image_uniforms(
        self,
        prog: moderngl.Program,
        frame: object,
        get_param: object,
        _set_uniform: object,
        ctx: moderngl.Context,
    ) -> None:
        """Upload all image-related uniforms. Call before vao.render()."""
        image_path = get_param("inner_image_path", "")
        self._update_image_texture(ctx, image_path)
        self._ensure_fallback_texture(ctx)

        has_image = self._image_texture is not None
        _set_uniform(prog, "u_image_enabled", 1 if has_image else 0)

        tex = self._image_texture if has_image else self._fallback_texture
        tex.use(location=1)
        _set_uniform(prog, "u_image_tex", 1)

        _set_uniform(prog, "u_image_padding", get_param("inner_image_padding", 0.0))

        img_bounce_on = get_param("inner_image_beat_bounce", False)
        shape_bounce_on = get_param("shape_beat_bounce", False)

        bounce = 0.0
        if img_bounce_on or shape_bounce_on:
            bounce = self._compute_bounce(frame.beat, frame.beat_intensity, frame.timestamp)

        img_bounce = (
            bounce * get_param("inner_image_bounce_strength", 0.15)
            if img_bounce_on else 0.0
        )
        _set_uniform(prog, "u_image_bounce", img_bounce)
        _set_uniform(
            prog, "u_image_bounce_zoom",
            1 if get_param("inner_image_bounce_zoom", False) else 0,
        )

        shape_bounce = (
            bounce * get_param("shape_bounce_strength", 0.15)
            if shape_bounce_on else 0.0
        )
        _set_uniform(prog, "u_shape_bounce", shape_bounce)

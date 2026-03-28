"""Render pipeline — orchestrates background, visualization, and post-processing."""

import logging
import math
import struct
from collections.abc import Callable

import moderngl
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.core.text_overlay import TextOverlay
from wavern.core.video_source import VideoSource
from wavern.presets.schema import (
    AudioReactiveConfig,
    BackgroundConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
    BackgroundMovements,
    BlendMode,
    ColorStop,
    GlobalEffects,
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


AUDIO_SOURCE_MAP: dict[str, Callable[[FrameAnalysis], float]] = {
    "amplitude": lambda f: f.amplitude_envelope,
    "bass": lambda f: f.band_envelopes.get("bass", 0.0),
    "beat": lambda f: f.beat_intensity,
    "mid": lambda f: f.band_envelopes.get("mid", 0.0),
    "treble": lambda f: f.band_envelopes.get("brilliance", 0.0),
}


def _resolve_effect_intensity(effect: BackgroundEffect, frame: FrameAnalysis) -> float:
    """Compute final effect intensity, optionally modulated by audio."""
    base = effect.intensity
    if effect.audio.enabled:
        audio_val = AUDIO_SOURCE_MAP[effect.audio.source](frame)
        return min(max(base * audio_val * effect.audio.sensitivity, 0.0), 1.0)
    return base


def _resolve_movement_intensity(movement: BackgroundMovement, frame: FrameAnalysis) -> float:
    """Compute final movement intensity, optionally modulated by audio."""
    base = movement.intensity
    if movement.audio.enabled:
        audio_val = AUDIO_SOURCE_MAP[movement.audio.source](frame)
        return min(max(base * audio_val * movement.audio.sensitivity, 0.0), 2.0)
    return base


def _any_bg_effect_enabled(effects: BackgroundEffects) -> bool:
    """Return True if any background effect is enabled."""
    return (
        effects.blur.enabled
        or effects.hue_shift.enabled
        or effects.saturation.enabled
        or effects.brightness.enabled
        or effects.pixelate.enabled
        or effects.posterize.enabled
        or effects.invert.enabled
    )


def _resolve_global_effect_intensity(
    intensity: float,
    audio: AudioReactiveConfig,
    frame: FrameAnalysis,
) -> float:
    """Compute final intensity for a global effect, optionally modulated by audio."""
    if audio.enabled:
        audio_val = AUDIO_SOURCE_MAP[audio.source](frame)
        return min(max(intensity * audio_val * audio.sensitivity, 0.0), 1.0)
    return intensity


def _any_global_effect_enabled(effects: GlobalEffects) -> bool:
    """Return True if any global effect is enabled."""
    return (
        effects.vignette.enabled
        or effects.chromatic_aberration.enabled
        or effects.glitch.enabled
        or effects.film_grain.enabled
        or effects.bloom.enabled
        or effects.scanlines.enabled
        or effects.color_shift.enabled
    )


class Renderer:
    """Orchestrates the per-frame rendering pipeline.

    This class is the single rendering path used by BOTH the real-time GUI preview
    and the offline video export. The only difference is the target FBO.
    """

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

        # Background effects pass (created lazily)
        self._bg_effects_fbo: moderngl.Framebuffer | None = None
        self._bg_effects_texture: moderngl.Texture | None = None
        self._bg_effects_prog: moderngl.Program | None = None
        self._bg_effects_vao: moderngl.VertexArray | None = None
        self._bg_effects_vbo: moderngl.Buffer | None = None
        self._bg_effects_resolution: tuple[int, int] | None = None

        # Global effects pass (created lazily)
        self._global_effects_fbo: moderngl.Framebuffer | None = None
        self._global_effects_texture: moderngl.Texture | None = None
        self._global_effects_prog: moderngl.Program | None = None
        self._global_effects_vao: moderngl.VertexArray | None = None
        self._global_effects_vbo: moderngl.Buffer | None = None
        self._global_effects_resolution: tuple[int, int] | None = None

        # Video overlay resources
        self._overlay_video_source: VideoSource | None = None
        self._overlay_texture: moderngl.Texture | None = None
        self._overlay_program: moderngl.Program | None = None
        self._overlay_vbo: moderngl.Buffer | None = None
        self._overlay_vao: moderngl.VertexArray | None = None
        self._overlay_video_path: str | None = None

        # Text overlay (created lazily)
        self._text_overlay: TextOverlay | None = None

        # Shader program cache — keyed by viz type name, persists across preset switches
        self._program_cache: dict[str, moderngl.Program] = {}

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
        self._bg_program = self.ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)

        # Fullscreen quad: two triangles, positions + texcoords
        vertices = np.array(
            [
                # x,    y,   u,   v
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self._bg_vbo = self.ctx.buffer(vertices.tobytes())
        self._bg_vao = self.ctx.vertex_array(
            self._bg_program,
            [(self._bg_vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _ensure_bg_effects_pass(self) -> None:
        """Lazily create the effects shader program and fullscreen quad."""
        if self._bg_effects_prog is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("bg_effects.frag")
        self._bg_effects_prog = self.ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)

        vertices = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self._bg_effects_vbo = self.ctx.buffer(vertices.tobytes())
        self._bg_effects_vao = self.ctx.vertex_array(
            self._bg_effects_prog,
            [(self._bg_effects_vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _ensure_bg_effects_fbo(self, resolution: tuple[int, int]) -> None:
        """Create or resize the intermediate FBO for the effects pass."""
        if self._bg_effects_resolution == resolution and self._bg_effects_fbo is not None:
            return
        self._release_bg_effects_fbo()
        self._bg_effects_texture = self.ctx.texture(resolution, 4)
        self._bg_effects_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._bg_effects_fbo = self.ctx.framebuffer(color_attachments=[self._bg_effects_texture])
        self._bg_effects_resolution = resolution

    def _release_bg_effects_fbo(self) -> None:
        """Release the effects intermediate FBO."""
        if self._bg_effects_fbo is not None:
            self._bg_effects_fbo.release()
            self._bg_effects_fbo = None
        if self._bg_effects_texture is not None:
            self._bg_effects_texture.release()
            self._bg_effects_texture = None
        self._bg_effects_resolution = None

    def _ensure_global_effects_pass(self) -> None:
        """Lazily create the global effects shader program and fullscreen quad."""
        if self._global_effects_prog is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("global_effects.frag")
        self._global_effects_prog = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        vertices = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self._global_effects_vbo = self.ctx.buffer(vertices.tobytes())
        self._global_effects_vao = self.ctx.vertex_array(
            self._global_effects_prog,
            [(self._global_effects_vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _ensure_global_effects_fbo(self, resolution: tuple[int, int]) -> None:
        """Create or resize the intermediate FBO for the global effects pass."""
        if self._global_effects_resolution == resolution and self._global_effects_fbo is not None:
            return
        self._release_global_effects_fbo()
        self._global_effects_texture = self.ctx.texture(resolution, 4)
        self._global_effects_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._global_effects_fbo = self.ctx.framebuffer(
            color_attachments=[self._global_effects_texture],
        )
        self._global_effects_resolution = resolution

    def _release_global_effects_fbo(self) -> None:
        """Release the global effects intermediate FBO."""
        if self._global_effects_fbo is not None:
            self._global_effects_fbo.release()
            self._global_effects_fbo = None
        if self._global_effects_texture is not None:
            self._global_effects_texture.release()
            self._global_effects_texture = None
        self._global_effects_resolution = None

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
            bg.type,
            bg.image_path,
            bg.video_path,
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
                        bg.image_path,
                        self._bg_texture.size,
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

    def _set_bg_movement_uniforms(
        self, movements: BackgroundMovements, frame: FrameAnalysis,
    ) -> None:
        """Upload per-movement uniforms to the background shader program."""
        prog = self._bg_program
        if prog is None:
            return

        if "u_time" in prog:
            prog["u_time"].value = frame.timestamp  # type: ignore[reportAttributeAccessIssue]

        movement_names = ("drift", "shake", "wave", "zoom_pulse", "breathe")
        for name in movement_names:
            mv: BackgroundMovement = getattr(movements, name)
            intensity = _resolve_movement_intensity(mv, frame)
            prefix = f"u_{name}"

            if f"{prefix}_enabled" in prog:
                prog[f"{prefix}_enabled"].value = int(mv.enabled)  # type: ignore[reportAttributeAccessIssue]
            if f"{prefix}_speed" in prog:
                prog[f"{prefix}_speed"].value = mv.speed  # type: ignore[reportAttributeAccessIssue]
            if f"{prefix}_intensity" in prog:
                prog[f"{prefix}_intensity"].value = intensity  # type: ignore[reportAttributeAccessIssue]

            # Drift-specific: angle
            if name == "drift" and f"{prefix}_angle" in prog:
                prog[f"{prefix}_angle"].value = math.radians(mv.angle)  # type: ignore[reportAttributeAccessIssue]

            # Clamp (not applicable to drift)
            if name != "drift" and f"{prefix}_clamp" in prog:
                prog[f"{prefix}_clamp"].value = int(mv.clamp_to_frame)  # type: ignore[reportAttributeAccessIssue]

    def _set_bg_effects_uniforms(
        self,
        effects: BackgroundEffects,
        frame: FrameAnalysis,
        resolution: tuple[int, int],
    ) -> None:
        """Upload effects uniforms to the bg_effects shader."""
        prog = self._bg_effects_prog
        if prog is None:
            return

        if "u_resolution" in prog:
            prog["u_resolution"].value = (float(resolution[0]), float(resolution[1]))  # type: ignore[reportAttributeAccessIssue]

        for name, effect in [
            ("blur", effects.blur),
            ("hue_shift", effects.hue_shift),
            ("saturation", effects.saturation),
            ("brightness", effects.brightness),
            ("pixelate", effects.pixelate),
            ("posterize", effects.posterize),
            ("invert", effects.invert),
        ]:
            intensity = _resolve_effect_intensity(effect, frame)
            enabled_key = f"u_{name}_enabled"
            intensity_key = f"u_{name}_intensity"
            if enabled_key in prog:
                prog[enabled_key].value = int(effect.enabled)  # type: ignore[reportAttributeAccessIssue]
            if intensity_key in prog:
                prog[intensity_key].value = intensity  # type: ignore[reportAttributeAccessIssue]

    def _set_global_effects_uniforms(
        self,
        effects: GlobalEffects,
        frame: FrameAnalysis,
        resolution: tuple[int, int],
    ) -> None:
        """Upload global effects uniforms to the shader."""
        prog = self._global_effects_prog
        if prog is None:
            return

        if "u_resolution" in prog:
            prog["u_resolution"].value = (float(resolution[0]), float(resolution[1]))  # type: ignore[reportAttributeAccessIssue]
        if "u_time" in prog:
            prog["u_time"].value = frame.timestamp  # type: ignore[reportAttributeAccessIssue]

        # Vignette
        v = effects.vignette
        v_intensity = _resolve_global_effect_intensity(v.intensity, v.audio, frame)
        if "u_vignette_enabled" in prog:
            prog["u_vignette_enabled"].value = int(v.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_vignette_intensity" in prog:
            prog["u_vignette_intensity"].value = v_intensity  # type: ignore[reportAttributeAccessIssue]
        shape_map = {"circular": 0, "rectangular": 1, "diamond": 2}
        if "u_vignette_shape" in prog:
            prog["u_vignette_shape"].value = shape_map.get(v.shape, 0)  # type: ignore[reportAttributeAccessIssue]

        # Chromatic aberration
        ca = effects.chromatic_aberration
        ca_intensity = _resolve_global_effect_intensity(ca.intensity, ca.audio, frame)
        if "u_chromatic_enabled" in prog:
            prog["u_chromatic_enabled"].value = int(ca.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_intensity" in prog:
            prog["u_chromatic_intensity"].value = ca_intensity  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_direction" in prog:
            prog["u_chromatic_direction"].value = 1 if ca.direction == "linear" else 0  # type: ignore[reportAttributeAccessIssue]
        if "u_chromatic_angle" in prog:
            prog["u_chromatic_angle"].value = math.radians(ca.angle)  # type: ignore[reportAttributeAccessIssue]

        # Glitch
        g = effects.glitch
        g_intensity = _resolve_global_effect_intensity(g.intensity, g.audio, frame)
        if "u_glitch_enabled" in prog:
            prog["u_glitch_enabled"].value = int(g.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_glitch_intensity" in prog:
            prog["u_glitch_intensity"].value = g_intensity  # type: ignore[reportAttributeAccessIssue]
        type_map = {"scanline": 0, "block": 1, "digital": 2}
        if "u_glitch_type" in prog:
            prog["u_glitch_type"].value = type_map.get(g.type, 0)  # type: ignore[reportAttributeAccessIssue]

        # Film grain
        fg = effects.film_grain
        fg_intensity = _resolve_global_effect_intensity(fg.intensity, fg.audio, frame)
        if "u_grain_enabled" in prog:
            prog["u_grain_enabled"].value = int(fg.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_grain_intensity" in prog:
            prog["u_grain_intensity"].value = fg_intensity  # type: ignore[reportAttributeAccessIssue]

        # Bloom
        bl = effects.bloom
        bl_intensity = _resolve_global_effect_intensity(bl.intensity, bl.audio, frame)
        if "u_bloom_enabled" in prog:
            prog["u_bloom_enabled"].value = int(bl.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_bloom_intensity" in prog:
            prog["u_bloom_intensity"].value = bl_intensity  # type: ignore[reportAttributeAccessIssue]
        if "u_bloom_threshold" in prog:
            prog["u_bloom_threshold"].value = bl.threshold  # type: ignore[reportAttributeAccessIssue]

        # Scanlines
        sl = effects.scanlines
        sl_intensity = _resolve_global_effect_intensity(sl.intensity, sl.audio, frame)
        if "u_scanline_enabled" in prog:
            prog["u_scanline_enabled"].value = int(sl.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_scanline_intensity" in prog:
            prog["u_scanline_intensity"].value = sl_intensity  # type: ignore[reportAttributeAccessIssue]
        if "u_scanline_density" in prog:
            prog["u_scanline_density"].value = sl.density  # type: ignore[reportAttributeAccessIssue]

        # Color shift
        cs = effects.color_shift
        cs_intensity = _resolve_global_effect_intensity(cs.intensity, cs.audio, frame)
        if "u_color_shift_enabled" in prog:
            prog["u_color_shift_enabled"].value = int(cs.enabled)  # type: ignore[reportAttributeAccessIssue]
        if "u_color_shift_intensity" in prog:
            prog["u_color_shift_intensity"].value = cs_intensity  # type: ignore[reportAttributeAccessIssue]

    def _apply_global_effects(
        self,
        fbo: moderngl.Framebuffer,
        frame: FrameAnalysis,
        resolution: tuple[int, int],
    ) -> None:
        """Run the global effects pass: copy fbo to intermediate, apply effects, write back."""
        assert self._preset is not None
        self._ensure_global_effects_pass()
        self._ensure_global_effects_fbo(resolution)
        assert self._global_effects_fbo is not None
        assert self._global_effects_texture is not None
        assert self._global_effects_prog is not None
        assert self._global_effects_vao is not None

        # Copy current fbo content to intermediate
        self.ctx.copy_framebuffer(dst=self._global_effects_fbo, src=fbo)

        # Render effects pass back to main fbo
        fbo.use()
        self.ctx.viewport = (0, 0, resolution[0], resolution[1])
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        self._global_effects_texture.use(location=0)
        if "u_scene" in self._global_effects_prog:
            self._global_effects_prog["u_scene"].value = 0  # type: ignore[reportAttributeAccessIssue]

        self._set_global_effects_uniforms(
            self._preset.global_effects,
            frame,
            resolution,
        )

        self._global_effects_vao.render(moderngl.TRIANGLE_STRIP)

    def _render_bg_quad(self, fbo: moderngl.Framebuffer, frame: FrameAnalysis) -> None:
        """Render the background texture as a fullscreen quad, with optional effects pass."""
        if self._bg_texture is None or self._bg_vao is None:
            return

        # Upload video frame if using video background
        if self._video_source is not None:
            frame_data = self._video_source.get_frame(frame.timestamp)
            self._bg_texture.write(frame_data.tobytes())

        # Check if any effects are enabled
        has_effects = self._preset is not None and _any_bg_effect_enabled(
            self._preset.background.effects
        )

        # Determine render target for the background pass
        if has_effects:
            assert self._preset is not None
            resolution = (fbo.width, fbo.height)
            self._ensure_bg_effects_pass()
            self._ensure_bg_effects_fbo(resolution)
            assert self._bg_effects_fbo is not None
            bg_target = self._bg_effects_fbo
        else:
            bg_target = fbo

        # --- Pass 1: Render background (UV transform + movement) ---
        bg_target.use()
        self.ctx.viewport = (0, 0, bg_target.width, bg_target.height)
        if has_effects:
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        self._bg_texture.use(location=0)
        self._bg_program["u_background"].value = 0  # type: ignore[reportAttributeAccessIssue]

        if self._preset is not None:
            bg = self._preset.background
            self._set_bg_movement_uniforms(bg.movements, frame)

            if "u_rotation" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_rotation"].value = math.radians(bg.rotation)  # type: ignore[reportAttributeAccessIssue]
            if "u_mirror_x" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_mirror_x"].value = int(bg.mirror_x)  # type: ignore[reportAttributeAccessIssue]
            if "u_mirror_y" in self._bg_program:  # type: ignore[reportOperatorIssue]
                self._bg_program["u_mirror_y"].value = int(bg.mirror_y)  # type: ignore[reportAttributeAccessIssue]

            if bg.movements.drift.enabled and self._bg_texture is not None:
                self._bg_texture.repeat_x = True
                self._bg_texture.repeat_y = True

        self._bg_vao.render(moderngl.TRIANGLE_STRIP)

        # --- Pass 2: Apply effects (if any enabled) ---
        if has_effects:
            assert self._preset is not None
            assert self._bg_effects_texture is not None
            assert self._bg_effects_prog is not None
            assert self._bg_effects_vao is not None

            fbo.use()
            self.ctx.viewport = (0, 0, fbo.width, fbo.height)

            self._bg_effects_texture.use(location=0)
            self._bg_effects_prog["u_background"].value = 0  # type: ignore[reportAttributeAccessIssue]

            resolution = (fbo.width, fbo.height)
            self._set_bg_effects_uniforms(self._preset.background.effects, frame, resolution)

            self._bg_effects_vao.render(moderngl.TRIANGLE_STRIP)

    def _apply_bg_effects_standalone(
        self,
        fbo: moderngl.Framebuffer,
        frame: FrameAnalysis,
        resolution: tuple[int, int],
    ) -> None:
        """Apply background effects to a solid/none background (no texture).

        Copies the already-cleared FBO content to the effects intermediate,
        then runs the bg_effects shader back to the main FBO.
        """
        assert self._preset is not None
        self._ensure_bg_effects_pass()
        self._ensure_bg_effects_fbo(resolution)
        assert self._bg_effects_fbo is not None
        assert self._bg_effects_texture is not None
        assert self._bg_effects_prog is not None
        assert self._bg_effects_vao is not None

        # Copy current fbo (solid color clear) to intermediate
        self.ctx.copy_framebuffer(dst=self._bg_effects_fbo, src=fbo)

        # Render effects pass back to main fbo
        fbo.use()
        self.ctx.viewport = (0, 0, resolution[0], resolution[1])

        self._bg_effects_texture.use(location=0)
        self._bg_effects_prog["u_background"].value = 0  # type: ignore[reportAttributeAccessIssue]

        self._set_bg_effects_uniforms(self._preset.background.effects, frame, resolution)

        self._bg_effects_vao.render(moderngl.TRIANGLE_STRIP)

    def _ensure_layer_fbos(self, resolution: tuple[int, int]) -> None:
        """Create or resize layer FBOs to match resolution."""
        if self._layer_fbo_resolution == resolution and len(self._layer_fbos) == len(self._layers):
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
        vertices = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
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

                cached_program = self._program_cache.get(layer_cfg.visualization_type)
                if cached_program is not None:
                    viz.initialize_with_program(cached_program)
                else:
                    viz.initialize()
                    if viz.program is not None:
                        self._program_cache[layer_cfg.visualization_type] = viz.program

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
        elif (
            self._preset is not None
            and self._bg_texture is None
            and not skip_bg
            and _any_bg_effect_enabled(self._preset.background.effects)
        ):
            # Solid/none backgrounds have no texture but can still use effects.
            # Copy the cleared FBO to the intermediate, apply effects, write back.
            self._apply_bg_effects_standalone(fbo, frame, resolution)

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
        if (
            visible_layer_indices
            and self._composite_prog is not None
            and self._composite_vao is not None
        ):
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
                if i < n
                else 0
                for i in range(7)
            ]

            self._composite_prog["u_layer_count"].value = n  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_layers"].write(struct.pack("7i", *sampler_values))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_opacities"].write(struct.pack("7f", *opacities))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_blend_modes"].write(struct.pack("7i", *blend_modes))  # type: ignore[reportAttributeAccessIssue]
            self._composite_prog["u_visible"].write(struct.pack("7i", *visible))  # type: ignore[reportAttributeAccessIssue]

            self._composite_vao.render(moderngl.TRIANGLE_STRIP)

        # Global effects — before overlays
        if (
            self._preset is not None
            and self._preset.global_effects.apply_stage == "before_overlays"
            and _any_global_effect_enabled(self._preset.global_effects)
        ):
            self._apply_global_effects(fbo, frame, resolution)

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

        # Global effects — after overlays
        if (
            self._preset is not None
            and self._preset.global_effects.apply_stage == "after_overlays"
            and _any_global_effect_enabled(self._preset.global_effects)
        ):
            self._apply_global_effects(fbo, frame, resolution)

    def _ensure_overlay_quad(self) -> None:
        """Lazily create the overlay fullscreen quad shader and VAO."""
        if self._overlay_program is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("overlay.frag")
        self._overlay_program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        vertices = np.array(
            [
                -1.0,
                -1.0,
                0.0,
                0.0,
                1.0,
                -1.0,
                1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
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
        arr = np.frombuffer(data, dtype=np.uint8).reshape(resolution[1], resolution[0], components)
        # Flip vertically (OpenGL has origin at bottom-left)
        return np.flipud(arr).copy()

    def ensure_offscreen_fbo(self, resolution: tuple[int, int]) -> moderngl.Framebuffer:
        """Create or resize the offscreen FBO for export rendering."""
        if self._offscreen_fbo is not None:
            if self._offscreen_texture is not None and self._offscreen_texture.size == resolution:
                return self._offscreen_fbo
            self._offscreen_fbo.release()
            if self._offscreen_texture is not None:
                self._offscreen_texture.release()

        self._offscreen_texture = self.ctx.texture(resolution, 4)
        self._offscreen_fbo = self.ctx.framebuffer(color_attachments=[self._offscreen_texture])
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
        self._release_bg_effects_fbo()
        if self._bg_effects_vao is not None:
            self._bg_effects_vao.release()
            self._bg_effects_vao = None
        if self._bg_effects_vbo is not None:
            self._bg_effects_vbo.release()
            self._bg_effects_vbo = None
        if self._bg_effects_prog is not None:
            self._bg_effects_prog.release()
            self._bg_effects_prog = None
        self._release_global_effects_fbo()
        if self._global_effects_vao is not None:
            self._global_effects_vao.release()
            self._global_effects_vao = None
        if self._global_effects_vbo is not None:
            self._global_effects_vbo.release()
            self._global_effects_vbo = None
        if self._global_effects_prog is not None:
            self._global_effects_prog.release()
            self._global_effects_prog = None
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

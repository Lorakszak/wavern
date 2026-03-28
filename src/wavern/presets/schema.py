"""Pydantic models for preset validation and serialization."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlendMode(str, Enum):
    """Blending mode for visualization rendering."""

    NORMAL = "normal"
    ADDITIVE = "additive"
    SCREEN = "screen"
    MULTIPLY = "multiply"


class OverlayBlendMode(str, Enum):
    """Blend mode for video overlay compositing."""

    ALPHA = "alpha"
    ADDITIVE = "additive"
    SCREEN = "screen"


class ColorStop(BaseModel):
    """A single color stop in a gradient."""

    position: float = Field(ge=0.0, le=1.0, description="Position in gradient, 0.0-1.0")
    color: str = Field(
        pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$",
        description="Hex color, e.g. #FF00AAFF",
    )


class AudioReactiveConfig(BaseModel):
    """Audio reactivity settings, reusable across effects and movement."""

    enabled: bool = False
    source: str = Field(
        default="amplitude",
        pattern=r"^(amplitude|bass|beat|mid|treble)$",
    )
    sensitivity: float = Field(default=1.0, ge=0.1, le=5.0)


class BackgroundEffect(BaseModel):
    """Single background effect with manual + audio-reactive control."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class BackgroundEffects(BaseModel):
    """Container for all background post-processing effects."""

    blur: BackgroundEffect = Field(default_factory=BackgroundEffect)
    hue_shift: BackgroundEffect = Field(default_factory=BackgroundEffect)
    saturation: BackgroundEffect = Field(default_factory=BackgroundEffect)
    brightness: BackgroundEffect = Field(default_factory=BackgroundEffect)
    pixelate: BackgroundEffect = Field(default_factory=BackgroundEffect)
    posterize: BackgroundEffect = Field(default_factory=BackgroundEffect)
    invert: BackgroundEffect = Field(default_factory=BackgroundEffect)


class VignetteEffect(BaseModel):
    """Vignette effect with shape selection."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    shape: str = Field(
        default="circular",
        pattern=r"^(circular|rectangular|diamond)$",
    )
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class ChromaticAberrationEffect(BaseModel):
    """Chromatic aberration with direction mode."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    direction: str = Field(
        default="radial",
        pattern=r"^(radial|linear)$",
    )
    angle: float = Field(default=0.0, ge=0.0, le=360.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class GlitchEffect(BaseModel):
    """Glitch effect with type selection."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    type: str = Field(
        default="scanline",
        pattern=r"^(scanline|block|digital)$",
    )
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class FilmGrainEffect(BaseModel):
    """Animated film grain noise overlay."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class BloomEffect(BaseModel):
    """Bloom/glow effect — bright areas bleed light outward."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class ScanlinesEffect(BaseModel):
    """CRT-style horizontal scanlines overlay."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    density: float = Field(default=0.5, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class ColorShiftEffect(BaseModel):
    """Global hue rotation applied to the entire composited frame."""

    enabled: bool = False
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class GlobalEffects(BaseModel):
    """Container for all global post-processing effects."""

    apply_stage: str = Field(
        default="before_overlays",
        pattern=r"^(before_overlays|after_overlays)$",
    )
    vignette: VignetteEffect = Field(default_factory=VignetteEffect)
    chromatic_aberration: ChromaticAberrationEffect = Field(
        default_factory=ChromaticAberrationEffect,
    )
    glitch: GlitchEffect = Field(default_factory=GlitchEffect)
    film_grain: FilmGrainEffect = Field(default_factory=FilmGrainEffect)
    bloom: BloomEffect = Field(default_factory=BloomEffect)
    scanlines: ScanlinesEffect = Field(default_factory=ScanlinesEffect)
    color_shift: ColorShiftEffect = Field(default_factory=ColorShiftEffect)


class BackgroundMovement(BaseModel):
    """Single background movement effect with independent controls."""

    enabled: bool = False
    speed: float = Field(default=1.0, ge=0.0, le=10.0)
    intensity: float = Field(default=0.5, ge=0.0, le=2.0)
    angle: float = Field(default=0.0, ge=0.0, le=360.0)
    clamp_to_frame: bool = Field(default=False)
    audio: AudioReactiveConfig = Field(default_factory=AudioReactiveConfig)


class BackgroundMovements(BaseModel):
    """Container for all background movement effects — multiple can be active."""

    drift: BackgroundMovement = Field(default_factory=BackgroundMovement)
    shake: BackgroundMovement = Field(default_factory=BackgroundMovement)
    wave: BackgroundMovement = Field(default_factory=BackgroundMovement)
    zoom_pulse: BackgroundMovement = Field(default_factory=BackgroundMovement)
    breathe: BackgroundMovement = Field(default_factory=BackgroundMovement)


class BackgroundConfig(BaseModel):
    """Background layer settings."""

    type: str = Field(default="solid", pattern=r"^(solid|image|gradient|none|video)$")
    color: str = Field(default="#000000")
    image_path: str | None = None
    video_path: str | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur_radius: float = Field(default=0.0, ge=0.0)
    scale_mode: str = Field(default="cover", pattern=r"^(cover|contain|stretch|tile)$")
    rotation: float = Field(default=0.0, ge=0.0, le=360.0)
    mirror_x: bool = Field(default=False)
    mirror_y: bool = Field(default=False)
    gradient_stops: list[ColorStop] = Field(
        default_factory=lambda: [
            ColorStop(position=0.0, color="#000000"),
            ColorStop(position=1.0, color="#FFFFFF"),
        ],
        description="Color stops for gradient background type",
    )
    movements: BackgroundMovements = Field(default_factory=BackgroundMovements)
    effects: BackgroundEffects = Field(default_factory=BackgroundEffects)


class VideoOverlayConfig(BaseModel):
    """Video overlay composited on top of the visualization."""

    enabled: bool = False
    video_path: str | None = None
    blend_mode: OverlayBlendMode = OverlayBlendMode.ADDITIVE
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    rotation: float = Field(default=0.0, ge=0.0, le=360.0)
    mirror_x: bool = Field(default=False)
    mirror_y: bool = Field(default=False)


class OverlayConfig(BaseModel):
    """Text overlay settings for title and countdown display."""

    title_enabled: bool = False
    title_text: str = Field(default="", max_length=200)
    countdown_enabled: bool = False
    countdown_format: str = Field(
        default="elapsed_total",
        pattern=r"^(elapsed_total|remaining|elapsed)$",
    )
    link_positions: bool = True
    title_x: float = Field(default=0.5, ge=0.0, le=1.0)
    title_y: float = Field(default=0.05, ge=0.0, le=1.0)
    countdown_x: float = Field(default=0.5, ge=0.0, le=1.0)
    countdown_y: float = Field(default=0.05, ge=0.0, le=1.0)
    font_family: str = Field(default="montserrat")
    font_bold: bool = False
    font_size: int = Field(default=28, ge=8, le=120)
    font_color: str = Field(default="#FFFFFF")
    font_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    outline_enabled: bool = False
    outline_color: str = Field(default="#000000")
    outline_width: int = Field(default=2, ge=1, le=10)
    shadow_enabled: bool = False
    shadow_color: str = Field(default="#000000")
    shadow_opacity: float = Field(default=0.7, ge=0.0, le=1.0)
    shadow_offset_x: int = Field(default=3, ge=-20, le=20)
    shadow_offset_y: int = Field(default=3, ge=-20, le=20)


class ProjectSettings(BaseModel):
    """Project-wide output settings — separate from visualization presets."""

    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 60
    container: str = "mp4"  # "mp4" | "webm" | "mov" | "gif"
    crf: int = 18
    output_dir: str = ""  # default: ./video/
    output_filename: str = ""  # default: derived from audio stem
    video_codec: str = ""  # empty = auto-select default for container
    quality_preset: str = "high"
    encoder_speed: str = "medium"
    audio_bitrate: str = "192k"
    prores_profile: int = 3
    gif_max_colors: int = 256
    gif_dither: bool = True
    gif_loop: int = 0  # 0 = infinite
    gif_scale: float = 1.0
    hw_accel: str = "auto"  # "auto" | "off"
    intro_path: str = ""  # transient — not persisted in presets
    outro_path: str = ""  # transient — not persisted in presets
    intro_keep_audio: bool = True
    outro_keep_audio: bool = True
    intro_fade_in: float = 0.0
    intro_fade_out: float = 0.0
    outro_fade_in: float = 0.0
    outro_fade_out: float = 0.0


class VisualizationParams(BaseModel):
    """Visualization type and its tunable parameters."""

    visualization_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class VisualizationLayer(BaseModel):
    """One visualization layer in the compositing stack."""

    visualization_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    blend_mode: BlendMode = BlendMode.NORMAL
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    visible: bool = True
    name: str = ""
    colors: list[str] = Field(default=["#00FFAA", "#FF00AA", "#FFAA00"])


class Preset(BaseModel):
    """Complete preset definition — the root model serialized to/from JSON."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")
    author: str = Field(default="")
    version: int = Field(default=1)

    layers: list[VisualizationLayer] = Field(min_length=1, max_length=7)

    color_palette: list[str] = Field(
        default=["#00FFAA", "#FF00AA", "#FFAA00"],
        description="Ordered list of hex colors the visualization cycles through",
    )

    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    video_overlay: VideoOverlayConfig = Field(default_factory=VideoOverlayConfig)
    global_effects: GlobalEffects = Field(default_factory=GlobalEffects)

    fft_size: int = Field(default=2048, ge=256, le=16384)
    smoothing: float = Field(default=0.3, ge=0.0, le=0.99)
    beat_sensitivity: float = Field(default=1.0, ge=0.1, le=5.0)

    fade_in: float = Field(default=0.0, ge=0.0, le=30.0, description="Fade-in duration in seconds")
    fade_out: float = Field(
        default=0.0, ge=0.0, le=30.0, description="Fade-out duration in seconds"
    )

    fps: int = Field(default=60, ge=24, le=144)

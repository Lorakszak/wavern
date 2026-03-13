"""Pydantic models for preset validation and serialization."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlendMode(str, Enum):
    """Blending mode for visualization rendering."""

    NORMAL = "normal"
    ADDITIVE = "additive"
    MULTIPLY = "multiply"


class ColorStop(BaseModel):
    """A single color stop in a gradient."""

    position: float = Field(ge=0.0, le=1.0, description="Position in gradient, 0.0-1.0")
    color: str = Field(
        pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$",
        description="Hex color, e.g. #FF00AAFF",
    )


class BackgroundConfig(BaseModel):
    """Background layer settings."""

    type: str = Field(default="solid", pattern=r"^(solid|image|gradient|none)$")
    color: str = Field(default="#000000")
    image_path: str | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur_radius: float = Field(default=0.0, ge=0.0)
    scale_mode: str = Field(default="cover", pattern=r"^(cover|contain|stretch|tile)$")
    gradient_stops: list[ColorStop] = Field(
        default_factory=lambda: [
            ColorStop(position=0.0, color="#000000"),
            ColorStop(position=1.0, color="#FFFFFF"),
        ],
        description="Color stops for gradient background type",
    )


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
    container: str = "mp4"  # "mp4" | "webm"
    crf: int = 18
    output_dir: str = ""  # default: ./video/


class VisualizationParams(BaseModel):
    """Visualization type and its tunable parameters."""

    visualization_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class Preset(BaseModel):
    """Complete preset definition — the root model serialized to/from JSON."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")
    author: str = Field(default="")
    version: int = Field(default=1)

    visualization: VisualizationParams

    color_palette: list[str] = Field(
        default=["#00FFAA", "#FF00AA", "#FFAA00"],
        description="Ordered list of hex colors the visualization cycles through",
    )
    color_gradient: list[ColorStop] = Field(default_factory=list)
    blend_mode: BlendMode = BlendMode.ADDITIVE

    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)

    fft_size: int = Field(default=2048, ge=256, le=16384)
    smoothing: float = Field(default=0.3, ge=0.0, le=0.99)
    beat_sensitivity: float = Field(default=1.0, ge=0.1, le=5.0)

    fps: int = Field(default=60, ge=24, le=144)

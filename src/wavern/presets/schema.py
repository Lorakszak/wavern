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

    fft_size: int = Field(default=2048, ge=256, le=16384)
    smoothing: float = Field(default=0.3, ge=0.0, le=0.99)
    beat_sensitivity: float = Field(default=1.0, ge=0.1, le=5.0)

    fps: int = Field(default=60, ge=24, le=144)

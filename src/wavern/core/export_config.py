"""ExportConfig dataclass — shared between export pipeline and ffmpeg command builder."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExportConfig:
    """Video export settings."""

    output_path: Path
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 60
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    video_bitrate: str = "8M"
    pixel_format: str = "yuv420p"
    container: str = "mp4"
    crf: int = 18
    encoder_speed: str = "medium"
    audio_bitrate: str = "192k"
    quality_preset: str = "high"
    prores_profile: int = 3
    gif_max_colors: int = 256
    gif_dither: bool = True
    gif_loop: int = 0
    gif_scale: float = 1.0
    hw_accel: str = "auto"  # "auto" | "off"
    intro_path: Path | None = None
    outro_path: Path | None = None
    intro_keep_audio: bool = True
    outro_keep_audio: bool = True
    intro_fade_in: float = 0.0
    intro_fade_out: float = 0.0
    outro_fade_in: float = 0.0
    outro_fade_out: float = 0.0

"""FFmpeg command builder for video encoding."""

from __future__ import annotations

import logging
from pathlib import Path

from wavern.core.codecs import get_codec_family
from wavern.core.hwaccel import (
    HWAccelBackend,
    build_hw_input_flags,
    get_hw_encoder,
    map_quality_to_hw,
)

from wavern.core.export_config import ExportConfig

logger = logging.getLogger(__name__)


def build_ffmpeg_cmd(
    config: ExportConfig,
    ffmpeg_bin: str,
    w: int,
    h: int,
    input_pix_fmt: str,
    output_pix_fmt: str,
    output_path: Path,
    *,
    force_software: bool = False,
) -> tuple[list[str], bool]:
    """Build the ffmpeg encoding command based on codec and quality settings.

    Attempts hardware-accelerated encoding when hw_accel is "auto" and a
    compatible GPU encoder is detected. Falls back to software encoding
    otherwise.

    Args:
        config: Export configuration (codec, quality, fps, etc.).
        ffmpeg_bin: Path to ffmpeg binary.
        w: Video width in pixels.
        h: Video height in pixels.
        input_pix_fmt: Raw input pixel format (e.g. "rgb24", "rgba").
        output_pix_fmt: Output pixel format for the encoder.
        output_path: Path for the output file.
        force_software: If True, skip HW encoder detection entirely.

    Returns:
        Tuple of (ffmpeg command args, whether HW encoding is used).
    """
    codec = config.video_codec
    family = get_codec_family(codec)

    needs_alpha = input_pix_fmt == "rgba"
    hw_enc = None
    if not force_software:
        hw_enc = get_hw_encoder(codec, config.hw_accel, needs_alpha=needs_alpha)

    cmd = [ffmpeg_bin, "-y"]

    if hw_enc is not None:
        hw_input_flags = build_hw_input_flags(hw_enc, input_pix_fmt)
        cmd.extend(hw_input_flags)

    cmd += [
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",
        "-pix_fmt", input_pix_fmt,
        "-r", str(config.fps),
        "-i", "pipe:0",
    ]

    using_hw = False
    if hw_enc is not None:
        logger.info(
            "Using HW encoder: %s (%s)",
            hw_enc.encoder_name, hw_enc.backend.value,
        )
        using_hw = True
        cmd += ["-c:v", hw_enc.encoder_name]
        cmd += map_quality_to_hw(hw_enc, config.crf, config.encoder_speed)
        if hw_enc.backend != HWAccelBackend.VAAPI:
            cmd += ["-pix_fmt", output_pix_fmt]
    elif family in ("x264", "x265"):
        cmd += [
            "-c:v", codec,
            "-preset", config.encoder_speed,
            "-crf", str(config.crf),
            "-pix_fmt", output_pix_fmt,
        ]
        if family == "x265":
            cmd += ["-tag:v", "hvc1"]
    elif family == "vp9":
        cmd += [
            "-c:v", codec,
            "-b:v", "0",
            "-crf", str(config.crf),
            "-row-mt", "1",
            "-speed", config.encoder_speed,
            "-pix_fmt", output_pix_fmt,
        ]
    elif family == "av1":
        cmd += [
            "-c:v", codec,
            "-b:v", "0",
            "-crf", str(config.crf),
            "-cpu-used", config.encoder_speed,
            "-row-mt", "1",
            "-pix_fmt", output_pix_fmt,
        ]
    elif family == "prores":
        cmd += [
            "-c:v", codec,
            "-profile:v", str(config.prores_profile),
            "-pix_fmt", output_pix_fmt,
        ]

    cmd.append(str(output_path))
    logger.debug("Built ffmpeg command: %s", cmd)
    return cmd, using_hw

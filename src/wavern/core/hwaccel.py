"""Hardware-accelerated video encoder detection and mapping.

Probes ffmpeg at runtime for available GPU encoders (NVENC, VAAPI, QSV, AMF)
and provides transparent mapping from software codecs to their hardware
equivalents with correct quality/speed flag translation.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HWAccelBackend(Enum):
    """Supported hardware acceleration backends, in priority order."""

    NVENC = "nvenc"
    QSV = "qsv"
    VAAPI = "vaapi"
    AMF = "amf"


# Priority order for backend selection when multiple are available
_BACKEND_PRIORITY = [
    HWAccelBackend.NVENC,
    HWAccelBackend.QSV,
    HWAccelBackend.VAAPI,
    HWAccelBackend.AMF,
]


@dataclass(frozen=True)
class HWEncoder:
    """A hardware encoder alternative for a software codec."""

    encoder_name: str
    backend: HWAccelBackend
    software_codec: str
    quality_flag: str  # "-cq", "-qp", "-global_quality"
    speed_flag: str | None  # "-preset" for nvenc/qsv, None for vaapi/amf
    speed_values: list[str] = field(default_factory=list)
    init_flags: list[str] = field(default_factory=list)
    supports_alpha: bool = False


# Software speed → NVENC preset mapping (p1=fastest, p7=slowest)
_SW_TO_NVENC_SPEED: dict[str, str] = {
    "ultrafast": "p1", "superfast": "p1", "veryfast": "p2",
    "faster": "p3", "fast": "p3", "medium": "p4",
    "slow": "p5", "slower": "p6", "veryslow": "p7",
    # VP9/AV1 numeric speeds (0=slowest, 8=fastest)
    "0": "p7", "1": "p6", "2": "p5", "3": "p5",
    "4": "p4", "5": "p3", "6": "p2", "7": "p2", "8": "p1",
}

# Software speed → QSV preset mapping
_SW_TO_QSV_SPEED: dict[str, str] = {
    "ultrafast": "veryfast", "superfast": "veryfast", "veryfast": "veryfast",
    "faster": "faster", "fast": "fast", "medium": "medium",
    "slow": "slow", "slower": "slower", "veryslow": "veryslow",
    "0": "veryslow", "1": "slower", "2": "slow", "3": "slow",
    "4": "medium", "5": "fast", "6": "faster", "7": "veryfast", "8": "veryfast",
}


# Complete mapping: software_codec → list of possible HW encoders
HW_ENCODER_MAP: dict[str, list[HWEncoder]] = {
    "libx264": [
        HWEncoder(
            "h264_nvenc", HWAccelBackend.NVENC, "libx264",
            quality_flag="-cq", speed_flag="-preset",
            speed_values=["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        ),
        HWEncoder(
            "h264_qsv", HWAccelBackend.QSV, "libx264",
            quality_flag="-global_quality", speed_flag="-preset",
            speed_values=["veryfast", "faster", "fast", "medium",
                          "slow", "slower", "veryslow"],
        ),
        HWEncoder(
            "h264_vaapi", HWAccelBackend.VAAPI, "libx264",
            quality_flag="-qp", speed_flag=None,
            init_flags=["-vaapi_device", "/dev/dri/renderD128"],
        ),
        HWEncoder(
            "h264_amf", HWAccelBackend.AMF, "libx264",
            quality_flag="-qp_i", speed_flag=None,
        ),
    ],
    "libx265": [
        HWEncoder(
            "hevc_nvenc", HWAccelBackend.NVENC, "libx265",
            quality_flag="-cq", speed_flag="-preset",
            speed_values=["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        ),
        HWEncoder(
            "hevc_qsv", HWAccelBackend.QSV, "libx265",
            quality_flag="-global_quality", speed_flag="-preset",
            speed_values=["veryfast", "faster", "fast", "medium",
                          "slow", "slower", "veryslow"],
        ),
        HWEncoder(
            "hevc_vaapi", HWAccelBackend.VAAPI, "libx265",
            quality_flag="-qp", speed_flag=None,
            init_flags=["-vaapi_device", "/dev/dri/renderD128"],
        ),
        HWEncoder(
            "hevc_amf", HWAccelBackend.AMF, "libx265",
            quality_flag="-qp_i", speed_flag=None,
        ),
    ],
    "libaom-av1": [
        HWEncoder(
            "av1_nvenc", HWAccelBackend.NVENC, "libaom-av1",
            quality_flag="-cq", speed_flag="-preset",
            speed_values=["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        ),
        HWEncoder(
            "av1_qsv", HWAccelBackend.QSV, "libaom-av1",
            quality_flag="-global_quality", speed_flag="-preset",
            speed_values=["veryfast", "faster", "fast", "medium",
                          "slow", "slower", "veryslow"],
        ),
        HWEncoder(
            "av1_vaapi", HWAccelBackend.VAAPI, "libaom-av1",
            quality_flag="-qp", speed_flag=None,
            init_flags=["-vaapi_device", "/dev/dri/renderD128"],
        ),
    ],
    "libvpx-vp9": [
        HWEncoder(
            "vp9_vaapi", HWAccelBackend.VAAPI, "libvpx-vp9",
            quality_flag="-qp", speed_flag=None,
            init_flags=["-vaapi_device", "/dev/dri/renderD128"],
        ),
        HWEncoder(
            "vp9_qsv", HWAccelBackend.QSV, "libvpx-vp9",
            quality_flag="-global_quality", speed_flag="-preset",
            speed_values=["veryfast", "faster", "fast", "medium",
                          "slow", "slower", "veryslow"],
        ),
    ],
}

# Module-level cache for detected encoders
_cached_available: dict[str, HWEncoder] | None = None


def detect_hw_encoders(ffmpeg_bin: str | None = None) -> dict[str, HWEncoder]:
    """Probe ffmpeg for available hardware encoders.

    Returns a dict mapping software codec IDs to the best available HW encoder.
    Priority: NVENC > QSV > VAAPI > AMF.
    Results are cached — subsequent calls return the cached result.

    Args:
        ffmpeg_bin: Path to ffmpeg binary. Auto-detected if None.

    Returns:
        Dict mapping software codec to the best available HWEncoder, e.g.
        {"libx264": HWEncoder("h264_nvenc", ...), "libx265": HWEncoder("hevc_nvenc", ...)}.
    """
    global _cached_available
    if _cached_available is not None:
        return _cached_available

    if ffmpeg_bin is None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin is None:
            logger.debug("ffmpeg not found, no HW encoders available")
            _cached_available = {}
            return _cached_available

    available_encoders: set[str] = set()
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-encoders", "-hide_banner"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.decode(errors="replace").splitlines():
                # Format: " V..... encoder_name  Description"
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].startswith("V"):
                    available_encoders.add(parts[1])
    except Exception:
        logger.debug("Failed to probe ffmpeg encoders", exc_info=True)

    # For each software codec, find the best available HW encoder by priority
    result_map: dict[str, HWEncoder] = {}
    for sw_codec, hw_options in HW_ENCODER_MAP.items():
        # Sort by backend priority
        for backend in _BACKEND_PRIORITY:
            for hw_enc in hw_options:
                if hw_enc.backend == backend and hw_enc.encoder_name in available_encoders:
                    result_map[sw_codec] = hw_enc
                    break
            if sw_codec in result_map:
                break

    if result_map:
        names = [f"{v.encoder_name} ({k})" for k, v in result_map.items()]
        logger.info("HW encoders detected: %s", ", ".join(names))
    else:
        logger.info("No hardware encoders detected, using software encoding")

    _cached_available = result_map
    return _cached_available


def clear_hw_cache() -> None:
    """Clear the cached detection results. Useful for testing."""
    global _cached_available
    _cached_available = None


def get_hw_encoder(
    software_codec: str,
    hw_accel: str = "auto",
    needs_alpha: bool = False,
) -> HWEncoder | None:
    """Get the best available hardware encoder for a software codec.

    Args:
        software_codec: Software codec ID (e.g. "libx264").
        hw_accel: "auto" to detect and use HW if available, "off" to skip.
        needs_alpha: If True, skip HW encoders (they don't support alpha well).

    Returns:
        HWEncoder if a hardware encoder is available and appropriate, None otherwise.
    """
    if hw_accel == "off":
        return None

    if needs_alpha:
        # HW encoders generally don't support yuva420p/alpha
        return None

    if software_codec not in HW_ENCODER_MAP:
        # No HW variants exist (ProRes, GIF)
        return None

    available = detect_hw_encoders()
    return available.get(software_codec)


def map_quality_to_hw(
    hw_encoder: HWEncoder,
    crf: int,
    encoder_speed: str,
) -> list[str]:
    """Convert software CRF + encoder speed to hardware encoder flags.

    Args:
        hw_encoder: The hardware encoder to generate flags for.
        crf: CRF value from software encoder settings (0-51).
        encoder_speed: Software encoder speed string (e.g. "medium", "4").

    Returns:
        List of ffmpeg arguments for quality and speed control.
    """
    args: list[str] = []

    # Quality flag
    args.extend([hw_encoder.quality_flag, str(crf)])

    # Speed flag (if the HW encoder supports it)
    if hw_encoder.speed_flag is not None and hw_encoder.speed_values:
        if hw_encoder.backend == HWAccelBackend.NVENC:
            mapped_speed = _SW_TO_NVENC_SPEED.get(encoder_speed, "p4")
        elif hw_encoder.backend == HWAccelBackend.QSV:
            mapped_speed = _SW_TO_QSV_SPEED.get(encoder_speed, "medium")
        else:
            mapped_speed = encoder_speed

        # Validate the mapped speed is in the encoder's allowed values
        if mapped_speed not in hw_encoder.speed_values:
            mapped_speed = hw_encoder.speed_values[len(hw_encoder.speed_values) // 2]

        args.extend([hw_encoder.speed_flag, mapped_speed])

    return args


def build_hw_input_flags(hw_encoder: HWEncoder, input_pix_fmt: str) -> list[str]:
    """Build ffmpeg input/init flags for hardware encoding.

    For VAAPI, this includes the device init and pixel format upload filter.
    For other backends, returns the init_flags from the encoder descriptor.

    Args:
        hw_encoder: The hardware encoder being used.
        input_pix_fmt: The raw input pixel format (e.g. "rgb24").

    Returns:
        List of ffmpeg arguments to prepend before the input specification.
    """
    flags = list(hw_encoder.init_flags)

    if hw_encoder.backend == HWAccelBackend.VAAPI:
        # VAAPI needs a filter to upload frames to GPU
        flags.extend(["-vf", "format=nv12,hwupload"])

    return flags

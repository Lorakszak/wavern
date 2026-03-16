"""Codec/container registry — maps containers to codecs, quality presets, and encoder speeds."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CodecDescriptor:
    """Describes a video codec and its capabilities."""

    codec_id: str
    display_name: str
    alpha: bool
    quality_system: str  # "crf" | "prores_profile" | "gif"


CONTAINER_CODECS: dict[str, list[CodecDescriptor]] = {
    "mp4": [
        CodecDescriptor("libx264", "H.264", alpha=False, quality_system="crf"),
        CodecDescriptor("libx265", "H.265/HEVC", alpha=False, quality_system="crf"),
    ],
    "webm": [
        CodecDescriptor("libvpx-vp9", "VP9", alpha=True, quality_system="crf"),
        CodecDescriptor("libaom-av1", "AV1", alpha=True, quality_system="crf"),
    ],
    "mov": [
        CodecDescriptor("prores_ks", "ProRes", alpha=True, quality_system="prores_profile"),
    ],
    "gif": [
        CodecDescriptor("gif", "GIF", alpha=False, quality_system="gif"),
    ],
}

# Codec family groupings for encoder speed lookups
_CODEC_FAMILIES: dict[str, str] = {
    "libx264": "x264",
    "libx265": "x265",
    "libvpx-vp9": "vp9",
    "libaom-av1": "av1",
    "prores_ks": "prores",
    "gif": "gif",
}

# Encoder speed options per codec family
ENCODER_SPEEDS: dict[str, list[str]] = {
    "x264": ["ultrafast", "superfast", "veryfast", "faster", "fast",
             "medium", "slow", "slower", "veryslow"],
    "x265": ["ultrafast", "superfast", "veryfast", "faster", "fast",
             "medium", "slow", "slower", "veryslow"],
    "vp9": ["0", "1", "2", "3", "4", "5", "6", "7", "8"],
    "av1": ["0", "1", "2", "3", "4", "5", "6", "7", "8"],
    "prores": [],  # ProRes has no speed control
    "gif": [],     # GIF has no speed control
}

# Quality presets — maps preset name to per-codec-family values
QUALITY_PRESETS: dict[str, dict] = {
    "highest": {
        "crf": 0,
        "x264_preset": "veryslow",
        "x265_preset": "veryslow",
        "vp9_speed": "0",
        "av1_cpu_used": "0",
        "prores_profile": 5,  # 4444XQ
    },
    "very_high": {
        "crf": 14,
        "x264_preset": "slow",
        "x265_preset": "slow",
        "vp9_speed": "1",
        "av1_cpu_used": "2",
        "prores_profile": 4,  # 4444
    },
    "high": {
        "crf": 18,
        "x264_preset": "medium",
        "x265_preset": "medium",
        "vp9_speed": "2",
        "av1_cpu_used": "4",
        "prores_profile": 3,  # HQ
    },
    "medium": {
        "crf": 23,
        "x264_preset": "medium",
        "x265_preset": "medium",
        "vp9_speed": "4",
        "av1_cpu_used": "5",
        "prores_profile": 2,  # Normal
    },
    "low": {
        "crf": 28,
        "x264_preset": "fast",
        "x265_preset": "fast",
        "vp9_speed": "5",
        "av1_cpu_used": "6",
        "prores_profile": 1,  # LT
    },
    "lowest": {
        "crf": 35,
        "x264_preset": "ultrafast",
        "x265_preset": "ultrafast",
        "vp9_speed": "8",
        "av1_cpu_used": "8",
        "prores_profile": 0,  # Proxy
    },
}

AUDIO_BITRATE_OPTIONS: list[str] = ["128k", "192k", "256k", "320k"]


def get_codecs_for_container(container: str) -> list[CodecDescriptor]:
    """Return available codecs for a container format."""
    return CONTAINER_CODECS.get(container, [])


def get_default_codec(container: str) -> str:
    """Return the default codec ID for a container."""
    codecs = CONTAINER_CODECS.get(container, [])
    if not codecs:
        raise ValueError(f"Unknown container: {container}")
    return codecs[0].codec_id


def supports_alpha(container: str, codec: str) -> bool:
    """Check if a container/codec pair supports alpha transparency."""
    for desc in CONTAINER_CODECS.get(container, []):
        if desc.codec_id == codec:
            return desc.alpha
    return False


def supports_audio(container: str) -> bool:
    """Check if a container supports audio tracks."""
    return container != "gif"


def get_codec_family(codec_id: str) -> str:
    """Return the codec family name for encoder speed lookups."""
    return _CODEC_FAMILIES.get(codec_id, "")


def get_quality_settings(preset_name: str, codec_id: str) -> dict:
    """Resolve a quality preset to concrete settings for a specific codec.

    Returns dict with keys: crf, encoder_speed, prores_profile (as applicable).
    """
    preset = QUALITY_PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"Unknown quality preset: {preset_name}")

    family = get_codec_family(codec_id)
    result: dict = {}

    if family in ("x264", "x265"):
        result["crf"] = preset["crf"]
        result["encoder_speed"] = preset[f"{family}_preset"]
    elif family == "vp9":
        result["crf"] = preset["crf"]
        result["encoder_speed"] = preset["vp9_speed"]
    elif family == "av1":
        result["crf"] = preset["crf"]
        result["encoder_speed"] = preset["av1_cpu_used"]
    elif family == "prores":
        result["prores_profile"] = preset["prores_profile"]
    # gif has no quality settings

    return result

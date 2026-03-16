"""Shared GUI constants for export and project settings."""

# Quality preset keys → display names (used in both export dialog and project settings)
QUALITY_PRESET_DISPLAY: list[tuple[str, str]] = [
    ("highest", "Highest"),
    ("very_high", "Very High"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("lowest", "Lowest"),
    ("custom", "Custom"),
]

# Apple ProRes profile IDs → display names
PRORES_PROFILES: list[tuple[int, str]] = [
    (0, "Proxy"),
    (1, "LT"),
    (2, "Normal"),
    (3, "HQ"),
    (4, "4444"),
    (5, "4444XQ"),
]

# Supported export file extensions
ALL_EXTENSIONS: tuple[str, ...] = (".mp4", ".webm", ".mov", ".gif")

# Aspect ratio → list of (width, height) resolution presets
RESOLUTION_PRESETS: dict[str, list[tuple[int, int]]] = {
    "16:9": [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)],
    "9:16": [(720, 1280), (1080, 1920), (1440, 2560)],
    "1:1": [(720, 720), (1080, 1080), (1440, 1440), (2160, 2160)],
    "4:3": [(960, 720), (1440, 1080), (1920, 1440)],
    "3:4": [(720, 960), (1080, 1440), (1440, 1920)],
    "21:9": [(2560, 1080), (3440, 1440), (5120, 2160)],
    "9:21": [(1080, 2560), (1440, 3440)],
    "2:3": [(720, 1080), (960, 1440), (1440, 2160)],
    "3:2": [(1080, 720), (1440, 960), (2160, 1440)],
}

# Aspect ratio options for the combo box
ASPECT_RATIOS: list[str] = [
    "1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "9:21", "2:3", "3:2", "Custom",
]

# Common FPS values
FPS_OPTIONS: list[int] = [24, 25, 30, 60, 120]

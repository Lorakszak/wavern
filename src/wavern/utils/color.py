"""Color conversion helpers."""

import colorsys


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color string to normalized RGB tuple (0.0-1.0).

    Args:
        hex_color: Color string like "#FF00AA" or "#ff00aa".

    Returns:
        Tuple of (r, g, b) floats in [0.0, 1.0].
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def hex_to_rgba(hex_color: str) -> tuple[float, float, float, float]:
    """Convert hex color string to normalized RGBA tuple (0.0-1.0).

    Accepts "#RRGGBB" (alpha defaults to 1.0) or "#RRGGBBAA".
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    a = int(hex_color[6:8], 16) / 255.0 if len(hex_color) == 8 else 1.0
    return (r, g, b, a)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert normalized RGB to hex string."""
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color to HSV tuple (h in [0,360], s/v in [0,1])."""
    r, g, b = hex_to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360.0, s, v)


def hsv_to_hex(h: float, s: float, v: float) -> str:
    """Convert HSV (h in [0,360], s/v in [0,1]) to hex string."""
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
    return rgb_to_hex(r, g, b)


def lerp_color(color_a: str, color_b: str, t: float) -> str:
    """Linearly interpolate between two hex colors.

    Args:
        color_a: Start hex color.
        color_b: End hex color.
        t: Interpolation factor in [0.0, 1.0].
    """
    r1, g1, b1 = hex_to_rgb(color_a)
    r2, g2, b2 = hex_to_rgb(color_b)
    r = r1 + (r2 - r1) * t
    g = g1 + (g2 - g1) * t
    b = b1 + (b2 - b1) * t
    return rgb_to_hex(r, g, b)

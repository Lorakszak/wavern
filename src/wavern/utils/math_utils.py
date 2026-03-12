"""Math utilities for smoothing, interpolation, and easing."""

import numpy as np
from numpy.typing import NDArray


def smooth(
    current: NDArray[np.float32],
    previous: NDArray[np.float32],
    factor: float,
) -> NDArray[np.float32]:
    """Exponential moving average smoothing.

    Args:
        current: Current frame values.
        previous: Previous frame values.
        factor: Smoothing factor in [0, 1). Higher = smoother (more of previous kept).

    Returns:
        Smoothed values.
    """
    return (previous * factor + current * (1.0 - factor)).astype(np.float32)


def normalize(data: NDArray[np.float32], floor: float = 1e-10) -> NDArray[np.float32]:
    """Normalize array to [0, 1] range."""
    max_val = max(np.max(np.abs(data)), floor)
    return (data / max_val).astype(np.float32)


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out function. t in [0,1] -> [0,1]."""
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_quad(t: float) -> float:
    """Quadratic ease-in-out function. t in [0,1] -> [0,1]."""
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def db_to_linear(db: float) -> float:
    """Convert decibels to linear scale."""
    return 10.0 ** (db / 20.0)


def linear_to_db(linear: float, floor: float = 1e-10) -> float:
    """Convert linear scale to decibels."""
    return 20.0 * np.log10(max(linear, floor))


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b."""
    return a + (b - a) * t

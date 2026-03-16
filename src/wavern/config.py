"""Centralised application config paths — XDG-aware directory resolution."""

import os
from pathlib import Path

APP_NAME = "wavern"


def get_config_directory() -> Path:
    """Return the wavern config directory, respecting XDG_CONFIG_HOME.

    Returns:
        ``~/.config/wavern/`` by default, or ``$XDG_CONFIG_HOME/wavern/``
        when the environment variable is set.
    """
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(config_home) / APP_NAME


def get_preset_directory() -> Path:
    """Return the user preset directory (``<config_dir>/presets/``)."""
    return get_config_directory() / "presets"


def get_favorites_path() -> Path:
    """Return the favorites JSON file path (``<config_dir>/favorites.json``)."""
    return get_config_directory() / "favorites.json"

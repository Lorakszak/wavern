"""Scoped change identifiers for efficient GUI update routing."""

import enum


class ChangeScope(enum.Enum):
    """Identifies what part of the preset changed.

    Used to route updates only to panels/sections that care about the change.
    New scopes can be added by extending this enum and adding a routing entry
    in MainWindow._SCOPE_ROUTES.
    """

    LAYER_PARAM = "layer_param"
    LAYER_COLORS = "layer_colors"
    LAYER_STRUCTURE = "layer_structure"
    BACKGROUND = "background"
    BACKGROUND_EFFECTS = "bg_effects"
    GLOBAL_EFFECTS = "global_effects"
    OVERLAY = "overlay"
    FADE = "fade"
    TEXT = "text"
    ANALYSIS = "analysis"
    FULL = "full"

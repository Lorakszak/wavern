"""Built-in visualizations — importing this module registers all built-in types."""

from wavern.visualizations.registry import VisualizationRegistry  # noqa: F401

# Import all built-in visualizations to trigger @register decorators
from wavern.visualizations import waveform  # noqa: F401
from wavern.visualizations import spectrum_bars  # noqa: F401
from wavern.visualizations import circular_spectrum  # noqa: F401
from wavern.visualizations import rect_spectrum  # noqa: F401
from wavern.visualizations import particles  # noqa: F401
from wavern.visualizations import smoky_waves  # noqa: F401
from wavern.visualizations import lissajous  # noqa: F401
from wavern.visualizations import radial_waveform  # noqa: F401
from wavern.visualizations import spectrogram  # noqa: F401
from wavern.visualizations import tunnel  # noqa: F401

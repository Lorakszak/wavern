# Wavern Plugins

Place custom visualization `.py` files here or in `~/.config/wavern/plugins/`.

Each plugin file should contain a class that extends `AbstractVisualization` and is decorated with `@register`:

```python
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

@register
class MyVisualization(AbstractVisualization):
    NAME = "my_viz"
    DISPLAY_NAME = "My Visualization"
    DESCRIPTION = "A custom visualization"
    CATEGORY = "abstract"
    PARAM_SCHEMA = {
        "speed": {"type": "float", "default": 1.0, "min": 0.1, "max": 5.0, "label": "Speed"},
    }

    def initialize(self) -> None: ...
    def render(self, frame, fbo, resolution) -> None: ...
    def cleanup(self) -> None: ...
```

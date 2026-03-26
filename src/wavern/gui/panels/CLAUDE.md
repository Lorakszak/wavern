# wavern/gui/panels — Agent Guide

## Purpose
Settings panels displayed inside the sidebar. Each panel targets one concern of the preset.

## Panel Inventory
| File | Responsibility |
|---|---|
| `visual_panel.py` | Coordinator: layer list + per-layer viz type/colors + background + overlay |
| `param_section.py` | Viz type combo + dynamic per-viz parameter widgets |
| `color_section.py` | Color palette editor (add/remove/reorder swatches) |
| `background_section.py` | Background type, solid/gradient/image/video, transform, movement, effects (all bg types) |
| `global_effects_section.py` | Global post-processing: vignette, chromatic aberration, glitch, film grain, bloom, scanlines, color shift |
| `overlay_section.py` | Overlay video, blend mode, opacity, rotation, mirror |
| `text_panel.py` | Text overlay: content, font, size, position, animation |
| `analysis_panel.py` | FFT size, smoothing, beat detection threshold/cooldown |
| `export_panel.py` | Quick export settings used in the sidebar (not the full dialog) |
| `resolution_section.py` | Aspect ratio, resolution presets, width/height spinboxes, FPS |
| `quality_section.py` | Format, codec, quality preset, CRF, encoder speed, ProRes, GIF |

## Section Widget Pattern
Sections are `QWidget` subclasses that own their UI fragment:

```python
class MySection(QWidget):
    my_changed = Signal()          # emit when any value changes

    def __init__(self, parent=None): ...
    def build(self, preset: Preset) -> None: ...   # first-time UI construction
    def update_values(self, preset: Preset) -> None: ...  # sync without rebuild
    def collect(self) -> dict: ...  # return current widget state as plain dict
```

Coordinators call `section.collect()` and unpack into the pydantic model:
```python
data = {**self._res_section.collect(), **self._quality_section.collect()}
settings = ProjectSettings(output_dir=..., **data)
```

## Signal Flow
```
section.my_changed → coordinator._on_section_changed() → coordinator.settings_changed
                                                        → MainWindow._apply_preset()
```

Sections never know about `MainWindow` or other panels — all coupling goes upward via signals.

## _rebuilding Flag
Set `self._rebuilding = True` before programmatically updating combo/spin values, and
check it at the top of every signal handler to avoid loops:
```python
def _on_value_changed(self) -> None:
    if self._rebuilding:
        return
    self.my_changed.emit()
```

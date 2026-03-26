# wavern/gui — Agent Guide

## Purpose
PySide6 GUI layer. Everything here may import Qt. Never import from `gui/` in `core/`.

## Module Inventory
| File | Responsibility |
|---|---|
| `main_window.py` | Top-level orchestrator: wires audio, renderer, panels, transport |
| `gl_widget.py` | `QOpenGLWidget` — drives live preview render loop |
| `sidebar.py` | Collapsible sidebar that hosts settings panels |
| `transport_bar.py` | Play/pause/seek/volume controls |
| `preset_panel.py` | Preset browser with search, filter, favorites |
| `project_settings_panel.py` | Coordinator for `ResolutionSection` + `QualitySection` |
| `export_dialog.py` | Export settings dialog + progress UI |
| `export_worker.py` | `ExportWorker(QThread)` — runs `ExportPipeline` off the main thread |
| `menu_builder.py` | Free function `build_menu_bar(...)` — returns `dict[str, QAction]` |
| `keyboard_handler.py` | `KeyboardHandler(QObject)` — app-level event filter for shortcuts |
| `favorites_store.py` | Persist favorited preset names to `~/.config/wavern/favorites.json` |
| `theme_manager.py` | Load and switch QSS themes |
| `constants.py` | Shared UI constants (quality presets, ProRes profiles, resolutions, FPS) |
| `layer_list_widget.py` | Multi-layer management: visibility, reorder, blend, opacity per layer |
| `background_picker.py` | Reusable color/image/video picker widget |
| `collapsible_section.py` | Animated collapsible container widget |
| `drag_spinbox.py` | Spinbox with click-drag value editing |
| `no_scroll_combo.py` | `QComboBox` that ignores scroll wheel to prevent accidental changes |
| `help_button.py` | `?` button that shows tooltip on click |
| `file_import_dialog.py` | Audio file import dialog |

## Signal Blocking Pattern
When rebuilding panel widgets programmatically, block signals before setting values:
```python
combo.blockSignals(True)
combo.setCurrentText(value)
combo.blockSignals(False)
```
Use the `_rebuilding: bool` flag on each panel to guard against cascading emissions
across dual sidebars when syncing left↔right.

## Dual Sidebar Sync
`MainWindow` maintains two `Sidebar` instances (left + right). Both display the same
preset. When one panel emits `params_changed`, `MainWindow` calls `update_values(preset)`
on the matching panel in the other sidebar to keep them in sync.

## Layer List Widget
`LayerListWidget` manages the multi-layer compositing stack (max 7 layers).
Each row has: visibility toggle, name, blend mode, opacity, move ▲/▼, delete.

- Buttons use `setObjectName("ColorControlBtn")` (▲/▼/x) and `"LayerEyeBtn"` (visibility)
  so the active QSS theme controls their appearance. Never hardcode button colors.
- Clicking anywhere on a row selects it (event filter on all child widgets).
- The selected layer determines which visualization/color settings are shown.
- `layer_order_changed(from_idx, to_idx)` signal notifies `VisualPanel` of reorders.

## Section Widget Pattern
Complex panels are decomposed into `QWidget` section subclasses:
- Each section owns its UI, builds itself, emits focused signals
- The coordinator panel creates sections inside `CollapsibleSection` containers
- Sections expose `collect() -> dict` for the coordinator to read current values
- See `panels/CLAUDE.md` for the full pattern

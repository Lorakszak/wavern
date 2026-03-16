# wavern/presets — Agent Guide

## Purpose
Preset schema definition and filesystem persistence.

## Files
| File | Responsibility |
|---|---|
| `schema.py` | `Preset` pydantic model (the canonical preset data shape) |
| `manager.py` | `PresetManager` — list, load, save, delete, import, export |

## Preset Model (`schema.py`)
`Preset` is a pydantic v2 model. Key fields:
- `name` — display name (used as identity key in the manager)
- `visualization_type` — matches `AbstractVisualization.NAME`
- `params` — `dict[str, Any]`, validated against `PARAM_SCHEMA` at render time
- `fft_size`, `smoothing` — audio analysis settings
- `background` — `BackgroundConfig` (type: solid/gradient/image/video/none)
- `overlay` — `OverlayConfig` (optional video overlay)
- `text_overlays` — list of `TextOverlayConfig`
- `project_settings` — `ProjectSettings` (resolution, fps, codec, quality)

Always use `Preset.model_validate(data)` to load from dict/JSON. Never construct manually.

## Preset Locations
- **Built-in**: `src/wavern/presets/defaults/*.json` — shipped with the package
- **User**: `~/.config/wavern/presets/*.json` — created by the user
- User presets shadow built-ins with the same `name` field

## PresetManager
```python
manager = PresetManager()              # uses ~/.config/wavern/presets/
manager = PresetManager(Path("/tmp"))  # override for testing

manager.list_presets()   # → list[dict] with name, source, path
manager.load("name")     # → Preset (user shadows builtin)
manager.save(preset)     # → Path (writes to user dir)
manager.delete("name")   # raises PresetError if not found or is builtin
```

## Adding a New Built-in Preset
1. Create `src/wavern/presets/defaults/my_preset.json`
2. Set `"name"` to a unique display string
3. Set `"visualization_type"` to an existing `NAME` from `visualizations/`
4. Validate with `uv run pytest tests/ -v -k preset`

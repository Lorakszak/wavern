"""Preset filesystem management — save, load, list, delete."""

import json
import logging
import re
from importlib import resources
from pathlib import Path
from typing import Any

from wavern.config import get_preset_directory
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


def _migrate_preset_data(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Migrate old single-viz format to multi-layer format."""
    default_palette = ["#00FFAA", "#FF00AA", "#FFAA00"]
    palette = raw_data.get("color_palette", default_palette)

    if "visualization" in raw_data and "layers" not in raw_data:
        viz = raw_data.pop("visualization")
        old_blend = raw_data.pop("blend_mode", "normal")
        raw_data.pop("color_gradient", None)
        raw_data["layers"] = [
            {
                "visualization_type": viz["visualization_type"],
                "params": viz.get("params", {}),
                "blend_mode": old_blend,
                "opacity": 1.0,
                "visible": True,
                "name": "",
                "colors": palette,
            }
        ]

    # Migrate color_override → colors on existing multi-layer presets
    if "layers" in raw_data:
        for layer in raw_data["layers"]:
            if "colors" not in layer:
                override = layer.pop("color_override", None)
                layer["colors"] = override if override else palette

    # Migrate single-movement to multi-movement format
    bg = raw_data.get("background")
    if isinstance(bg, dict) and "movement" in bg and "movements" not in bg:
        old_mv = bg.pop("movement")
        mv_type = old_mv.get("type", "none")
        if mv_type != "none":
            new_mv = {k: v for k, v in old_mv.items() if k != "type"}
            new_mv["enabled"] = True
            bg["movements"] = {mv_type: new_mv}

    return raw_data


class PresetError(Exception):
    """Raised for preset load/save failures."""


def _slugify(name: str) -> str:
    """Convert a preset name to a safe filename slug.

    Raises:
        PresetError: If the name produces an empty slug.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    if not slug:
        raise PresetError(f"Preset name produces an empty slug: {name!r}")
    return slug


class PresetManager:
    """Handles persistence of presets to the filesystem.

    Presets live in two locations:
    - Built-in: shipped inside the package at wavern/presets/defaults/
    - User: stored in ~/.config/wavern/presets/ (XDG_CONFIG_HOME respected)

    User presets take precedence over built-ins with the same name.
    """

    def __init__(self, user_preset_dir: Path | None = None) -> None:
        self._user_dir = user_preset_dir or get_preset_directory()
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_cache: list[dict[str, str]] | None = None
        logger.debug("Preset directories: user=%s", self._user_dir)

    @property
    def user_dir(self) -> Path:
        return self._user_dir

    def _builtin_dir(self) -> Path:
        """Get the path to the built-in defaults directory."""
        return Path(str(resources.files("wavern.presets") / "defaults"))

    def _invalidate_cache(self) -> None:
        """Clear the metadata cache so the next list call re-reads disk."""
        self._metadata_cache = None

    def _list_presets_uncached(self) -> list[dict[str, str]]:
        """Return list of available presets with name, source, and path."""
        presets: dict[str, dict[str, str]] = {}

        # Built-in presets
        builtin_dir = self._builtin_dir()
        if builtin_dir.exists():
            for f in sorted(builtin_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    name = data.get("name", f.stem)
                    presets[name] = {"name": name, "source": "builtin", "path": str(f)}
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping invalid built-in preset %s: %s", f, e)

        # User presets (shadow built-ins)
        for f in sorted(self._user_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("name", f.stem)
                presets[name] = {"name": name, "source": "user", "path": str(f)}
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping invalid user preset %s: %s", f, e)

        return list(presets.values())

    def list_presets_with_type(self) -> list[dict[str, str]]:
        """Return preset metadata including visualization_type, with caching.

        Results are cached after the first call. The cache is invalidated
        by save(), delete(), and import_preset().
        """
        if self._metadata_cache is not None:
            return self._metadata_cache

        result = []
        for entry in self._list_presets_uncached():
            try:
                raw = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
                raw = _migrate_preset_data(raw)
                layers = raw.get("layers", [])
                viz_type = layers[0]["visualization_type"] if layers else ""
            except Exception:
                viz_type = ""
            result.append({**entry, "visualization_type": viz_type})

        self._metadata_cache = result
        return self._metadata_cache

    def list_presets(self) -> list[dict[str, str]]:
        """Return list of available presets with name, source, and path.

        Derives from the cached list_presets_with_type() result, stripping
        the visualization_type field.
        """
        return [
            {k: v for k, v in entry.items() if k != "visualization_type"}
            for entry in self.list_presets_with_type()
        ]

    def load(self, name: str) -> Preset:
        """Load a preset by name. User presets shadow built-ins.

        Raises:
            PresetError: If preset not found or JSON is invalid.
        """
        # Check user dir first
        for f in self._user_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name") == name:
                    data = _migrate_preset_data(data)
                    return Preset.model_validate(data)
            except Exception:
                logger.warning("Failed to load user preset %s: %s", f, exc_info=True)
                continue

        # Check built-in dir
        builtin_dir = self._builtin_dir()
        if builtin_dir.exists():
            for f in builtin_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("name") == name:
                        data = _migrate_preset_data(data)
                        return Preset.model_validate(data)
                except Exception:
                    logger.warning("Failed to load built-in preset %s", f, exc_info=True)
                    continue

        raise PresetError(f"Preset not found: {name}")

    def load_from_path(self, path: Path) -> Preset:
        """Load a preset from an arbitrary file path."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data = _migrate_preset_data(data)
            return Preset.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            raise PresetError(f"Failed to load preset from {path}: {e}") from e

    def save(self, preset: Preset) -> Path:
        """Save a preset to the user preset directory. Returns the file path."""
        self._invalidate_cache()
        filename = _slugify(preset.name) + ".json"
        path = self._user_dir / filename
        path.write_text(
            preset.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Saved preset '%s' to %s", preset.name, path)
        return path

    def delete(self, name: str) -> None:
        """Delete a user preset.

        Raises:
            PresetError: If preset not found or is a built-in.
        """
        self._invalidate_cache()
        for f in self._user_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name") == name:
                    f.unlink()
                    logger.info("Deleted preset '%s'", name)
                    return
            except Exception:
                logger.warning("Failed to read preset %s during delete", f, exc_info=True)
                continue

        raise PresetError(f"User preset not found: {name}")

    def export_preset(self, name: str, target_path: Path) -> None:
        """Export a preset to an arbitrary path (for sharing)."""
        preset = self.load(name)
        target_path.write_text(
            preset.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def import_preset(self, source_path: Path) -> Preset:
        """Import a preset from an arbitrary path into the user directory."""
        self._invalidate_cache()
        preset = self.load_from_path(source_path)
        self.save(preset)
        return preset

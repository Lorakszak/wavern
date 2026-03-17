"""Preset filesystem management — save, load, list, delete."""

import json
import logging
import re
from importlib import resources
from pathlib import Path

from wavern.config import get_preset_directory
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


class PresetError(Exception):
    """Raised for preset load/save failures."""


def _slugify(name: str) -> str:
    """Convert a preset name to a safe filename slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
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

    @property
    def user_dir(self) -> Path:
        return self._user_dir

    def _builtin_dir(self) -> Path:
        """Get the path to the built-in defaults directory."""
        return Path(str(resources.files("wavern.presets") / "defaults"))

    def list_presets(self) -> list[dict[str, str]]:
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
        """Return preset metadata including visualization_type, without full validation."""
        result = []
        for entry in self.list_presets():
            try:
                raw = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
                viz_type = raw.get("visualization", {}).get("visualization_type", "")
            except Exception:
                viz_type = ""
            result.append({**entry, "visualization_type": viz_type})
        return result

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
                    return Preset.model_validate(data)
            except (json.JSONDecodeError, Exception):
                continue

        # Check built-in dir
        builtin_dir = self._builtin_dir()
        if builtin_dir.exists():
            for f in builtin_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("name") == name:
                        return Preset.model_validate(data)
                except (json.JSONDecodeError, Exception):
                    continue

        raise PresetError(f"Preset not found: {name}")

    def load_from_path(self, path: Path) -> Preset:
        """Load a preset from an arbitrary file path."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Preset.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            raise PresetError(f"Failed to load preset from {path}: {e}") from e

    def save(self, preset: Preset) -> Path:
        """Save a preset to the user preset directory. Returns the file path."""
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
        for f in self._user_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name") == name:
                    f.unlink()
                    logger.info("Deleted preset '%s'", name)
                    return
            except (json.JSONDecodeError, Exception):
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
        preset = self.load_from_path(source_path)
        self.save(preset)
        return preset

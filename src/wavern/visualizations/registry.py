"""Visualization registry — singleton that maps names to visualization classes."""

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Type

from wavern.visualizations.base import AbstractVisualization

logger = logging.getLogger(__name__)


class VisualizationRegistry:
    """Singleton registry mapping visualization names to their classes.

    Built-in visualizations are registered at import time via the @register decorator.
    External plugins are discovered by scanning a plugins directory.
    """

    _instance: "VisualizationRegistry | None" = None
    _registry: dict[str, Type[AbstractVisualization]]

    def __new__(cls) -> "VisualizationRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry = {}
        return cls._instance

    def register(
        self, viz_class: Type[AbstractVisualization]
    ) -> Type[AbstractVisualization]:
        """Register a visualization class. Can be used as a decorator.

        Raises:
            ValueError: If a visualization with the same NAME is already registered.
        """
        name = viz_class.NAME
        if name in self._registry:
            raise ValueError(
                f"Visualization '{name}' is already registered "
                f"by {self._registry[name].__name__}"
            )
        self._registry[name] = viz_class
        logger.debug("Registered visualization: %s (%s)", name, viz_class.__name__)
        return viz_class

    def get(self, name: str) -> Type[AbstractVisualization]:
        """Look up a visualization class by its NAME.

        Raises:
            KeyError: If name is not registered.
        """
        if name not in self._registry:
            available = ", ".join(sorted(self._registry.keys()))
            raise KeyError(f"Unknown visualization: '{name}'. Available: {available}")
        return self._registry[name]

    def list_all(self) -> list[dict[str, str]]:
        """Return list of registered visualizations with metadata."""
        return [
            {
                "name": cls.NAME,
                "display_name": cls.DISPLAY_NAME,
                "category": cls.CATEGORY,
                "description": cls.DESCRIPTION,
            }
            for cls in self._registry.values()
        ]

    def list_names(self) -> list[str]:
        """Return sorted list of registered visualization names."""
        return sorted(self._registry.keys())

    def load_plugins(self, plugin_dir: str) -> list[str]:
        """Scan plugin_dir for .py files, import them, collect any @register'd classes.

        Returns list of newly registered visualization names.
        """
        path = Path(plugin_dir)
        if not path.exists():
            return []

        before = set(self._registry.keys())

        for py_file in sorted(path.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(
                    py_file.stem, py_file,
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                logger.info("Loaded plugin: %s", py_file.name)
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", py_file.name, e)

        # Also check for package plugins (directories with __init__.py)
        for pkg_dir in sorted(path.iterdir()):
            init_file = pkg_dir / "__init__.py"
            if pkg_dir.is_dir() and init_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        pkg_dir.name, init_file,
                        submodule_search_locations=[str(pkg_dir)],
                    )
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info("Loaded plugin package: %s", pkg_dir.name)
                except Exception as e:
                    logger.warning("Failed to load plugin package %s: %s", pkg_dir.name, e)

        after = set(self._registry.keys())
        return sorted(after - before)


# Module-level singleton and decorator
_registry = VisualizationRegistry()


def register(cls: Type[AbstractVisualization]) -> Type[AbstractVisualization]:
    """Decorator to register a visualization class with the global registry."""
    return _registry.register(cls)

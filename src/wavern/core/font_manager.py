"""Font manager — downloads and caches curated fonts for text overlays.

Fonts are downloaded from Google Fonts (OFL-licensed) on first use and
cached inside the package at ``src/wavern/fonts/``. A background preload
thread downloads all fonts at app startup so they're ready before the
user picks one.

Variable fonts (single file with weight axis) are used where available.
Bold is selected by setting the ``wght`` axis to 700 via Pillow's
``set_variation_by_axes``.
"""

import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import NamedTuple

from PIL import ImageFont

logger = logging.getLogger(__name__)

# Track background preload state
_preload_lock = threading.Lock()
_preload_thread: threading.Thread | None = None
_preload_done = threading.Event()

# Fonts are cached inside the package directory
_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

# Base URL for raw font files from Google Fonts GitHub repo (OFL-licensed)
_GF_BASE = "https://github.com/google/fonts/raw/main"


class FontEntry(NamedTuple):
    """A single font in the catalog."""

    display_name: str
    filename: str
    url: str
    variable: bool  # True = variable font with wght axis


# Curated font catalog — all OFL-licensed from Google Fonts
FONT_CATALOG: dict[str, FontEntry] = {
    "montserrat": FontEntry(
        display_name="Montserrat",
        filename="Montserrat.ttf",
        url=f"{_GF_BASE}/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
        variable=True,
    ),
    "bebas_neue": FontEntry(
        display_name="Bebas Neue",
        filename="BebasNeue-Regular.ttf",
        url=f"{_GF_BASE}/ofl/bebasneue/BebasNeue-Regular.ttf",
        variable=False,
    ),
    "roboto": FontEntry(
        display_name="Roboto",
        filename="Roboto.ttf",
        url=f"{_GF_BASE}/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
        variable=True,
    ),
    "oswald": FontEntry(
        display_name="Oswald",
        filename="Oswald.ttf",
        url=f"{_GF_BASE}/ofl/oswald/Oswald%5Bwght%5D.ttf",
        variable=True,
    ),
    "space_mono": FontEntry(
        display_name="Space Mono",
        filename="SpaceMono-Regular.ttf",
        url=f"{_GF_BASE}/ofl/spacemono/SpaceMono-Regular.ttf",
        variable=False,
    ),
    "inter": FontEntry(
        display_name="Inter",
        filename="Inter.ttf",
        url=f"{_GF_BASE}/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
        variable=True,
    ),
}

# Separate bold files only for non-variable fonts
_BOLD_VARIANTS: dict[str, tuple[str, str]] = {
    "space_mono": (
        "SpaceMono-Bold.ttf",
        f"{_GF_BASE}/ofl/spacemono/SpaceMono-Bold.ttf",
    ),
}


def _ensure_fonts_dir() -> Path:
    """Create the fonts cache directory if it doesn't exist."""
    _FONTS_DIR.mkdir(parents=True, exist_ok=True)
    return _FONTS_DIR


def _download_font(filename: str, url: str) -> Path | None:
    """Download a font file to the fonts directory. Returns path or None."""
    fonts_dir = _ensure_fonts_dir()
    dest = fonts_dir / filename

    if dest.exists():
        return dest

    logger.info("Downloading font: %s", filename)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "wavern-font-manager/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.rename(dest)
        logger.info("Font cached: %s", dest)
        return dest
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        logger.warning("Failed to download font %s: %s", filename, e)
        return None


def preload_all_fonts() -> None:
    """Download all fonts in the catalog in a background thread.

    Call this at app startup so fonts are cached before the user
    picks one. Safe to call multiple times — only runs once.
    """
    global _preload_thread
    with _preload_lock:
        if _preload_thread is not None:
            return

        def _worker() -> None:
            for key, entry in FONT_CATALOG.items():
                _download_font(entry.filename, entry.url)
            for filename, url in _BOLD_VARIANTS.values():
                _download_font(filename, url)
            _preload_done.set()
            logger.info("All fonts preloaded")

        _preload_thread = threading.Thread(target=_worker, daemon=True, name="font-preload")
        _preload_thread.start()


def _load_font(
    path: Path, size: int, bold: bool, variable: bool,
) -> ImageFont.FreeTypeFont:
    """Load a font file and optionally set bold weight for variable fonts."""
    font = ImageFont.truetype(str(path), size)
    if bold and variable:
        try:
            axes = font.get_variation_axes()
            axis_values = []
            for axis in axes:
                if axis["tag"] == "wght":  # type: ignore[reportGeneralTypeIssues]
                    axis_values.append(700)  # Bold weight
                elif axis["tag"] == "opsz":  # type: ignore[reportGeneralTypeIssues]
                    axis_values.append(axis.get("default", 14))
                elif axis["tag"] == "wdth":  # type: ignore[reportGeneralTypeIssues]
                    axis_values.append(axis.get("default", 100))
                else:
                    axis_values.append(axis.get("default", axis["minimum"]))
            font.set_variation_by_axes(axis_values)
        except Exception as e:
            logger.debug("Could not set bold variation: %s", e)
    return font


def get_font(
    family: str = "montserrat",
    size: int = 28,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font from the catalog at the given size.

    If the font file is already cached (from preload or prior use), loads
    instantly. If not cached yet, falls back to any cached font or PIL
    default to avoid blocking the render loop on a network download.

    Args:
        family: Key from FONT_CATALOG (e.g. "montserrat", "bebas_neue").
        size: Font size in pixels.
        bold: Use bold variant if available.

    Returns:
        A PIL font object ready for ImageDraw.text().
    """
    entry = FONT_CATALOG.get(family)
    if entry is None:
        entry = FONT_CATALOG["montserrat"]

    fonts_dir = _ensure_fonts_dir()

    # For non-variable fonts with a separate bold file
    if bold and not entry.variable and family in _BOLD_VARIANTS:
        bold_filename, _ = _BOLD_VARIANTS[family]
        bold_path = fonts_dir / bold_filename
        if bold_path.exists():
            try:
                return ImageFont.truetype(str(bold_path), size)
            except Exception:
                pass

    # Try loading the cached font file
    cached_path = fonts_dir / entry.filename
    if cached_path.exists():
        try:
            return _load_font(cached_path, size, bold, entry.variable)
        except Exception as e:
            logger.warning("Failed to load cached font %s: %s", cached_path, e)

    # Font not cached yet — try any other cached font as fallback
    for cached in fonts_dir.glob("*.ttf"):
        try:
            return ImageFont.truetype(str(cached), size)
        except Exception:
            continue

    # Nothing cached at all -- fall back to PIL default rather than blocking
    # the render loop with a synchronous download.  preload_all_fonts() should
    # have cached everything at startup; if we reach here, something went wrong.
    logger.warning(
        "Font '%s' is not cached and cannot be loaded without a blocking download; "
        "falling back to PIL default.  Ensure preload_all_fonts() ran at startup.",
        family,
    )
    return ImageFont.load_default()


def list_available_fonts() -> list[tuple[str, str]]:
    """Return list of (key, display_name) for all fonts in the catalog."""
    return [(key, entry.display_name) for key, entry in FONT_CATALOG.items()]

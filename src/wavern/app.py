"""Application bootstrap — sets up Qt and launches the main window."""

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap, QSurfaceFormat
from PySide6.QtWidgets import QApplication

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def create_app() -> QApplication:
    """Create and configure the QApplication with proper OpenGL settings."""
    # Must set surface format BEFORE creating QApplication
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setSwapInterval(1)  # vsync
    fmt.setSamples(4)  # MSAA
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("Wavern")
    app.setApplicationVersion("0.1.0")

    icon_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
    pixmap = QPixmap(str(icon_path))
    app.setWindowIcon(QIcon(pixmap))

    return app


def run_gui(
    audio_path: Path | None = None,
    preset_name: str | None = None,
) -> int:
    """Launch the GUI application.

    Args:
        audio_path: Optional path to an audio file to load on startup.
        preset_name: Optional preset name to load on startup.

    Returns:
        Application exit code.
    """
    app = create_app()

    # Apply saved theme
    from wavern.gui.theme_manager import ThemeManager
    theme_mgr = ThemeManager()
    theme_mgr.apply(app, theme_mgr.load_preference())

    # Pre-download all fonts in background so they're cached before user picks one
    from wavern.core.font_manager import preload_all_fonts
    preload_all_fonts()

    # Import here to avoid circular imports and ensure GL context is set up
    from wavern.gui.main_window import MainWindow

    # Import visualizations to trigger registration
    import wavern.visualizations  # noqa: F401

    window = MainWindow(audio_path=audio_path, preset_name=preset_name)
    window.show()

    logger.info("Wavern GUI started")
    return app.exec()

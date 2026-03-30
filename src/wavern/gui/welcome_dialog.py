"""One-time welcome dialog shown on first launch."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.config import get_config_directory

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "welcome.json"
_SHOWCASE_DIR = Path(__file__).parent.parent / "assets" / "showcase"


class WelcomeAction:
    """Result of the welcome dialog interaction."""

    NONE = "none"
    LOAD_SHOWCASE = "load_showcase"
    OPEN_AUDIO = "open_audio"


def _settings_path() -> Path:
    """Return path to the welcome settings file."""
    return get_config_directory() / _SETTINGS_FILE


def should_show_welcome() -> bool:
    """Check if the welcome dialog should be shown.

    Returns True if the dialog has never been dismissed with 'don't show again'.
    """
    path = _settings_path()
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return not data.get("dismissed", False)
    except (json.JSONDecodeError, OSError):
        return True


def _save_dismissed() -> None:
    """Persist the 'don't show again' flag."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"dismissed": True}), encoding="utf-8")


def get_showcase_audio_path() -> Path | None:
    """Return the path to the showcase audio file, if it exists."""
    path = _SHOWCASE_DIR / "audio.mp3"
    return path if path.exists() else None


def get_showcase_background_path() -> Path | None:
    """Return the path to the showcase background image, if it exists."""
    path = _SHOWCASE_DIR / "background.png"
    return path if path.exists() else None


def get_showcase_logo_path() -> Path | None:
    """Return the path to the showcase logo image, if it exists."""
    path = _SHOWCASE_DIR / "logo.png"
    return path if path.exists() else None


class WelcomeDialog(QDialog):
    """First-launch welcome dialog with showcase and import options."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to Wavern")
        self.setFixedSize(480, 380)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._action = WelcomeAction.NONE
        self._setup_ui()

        # Center on screen
        screen = self.screen()
        if screen is not None:
            screen_geo = screen.availableGeometry()
            self.move(
                screen_geo.x() + (screen_geo.width() - self.width()) // 2,
                screen_geo.y() + (screen_geo.height() - self.height()) // 2,
            )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        # Logo
        logo_path = _SHOWCASE_DIR / "logo.png"
        if logo_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaledToHeight(120, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        # Title
        title = QLabel("Wavern")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Audio Visualizer")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; opacity: 0.7;")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._showcase_btn = QPushButton("Load Showcase")
        self._showcase_btn.setMinimumHeight(40)
        self._showcase_btn.setToolTip("Load demo audio with a showcase preset")
        self._showcase_btn.clicked.connect(self._on_showcase)
        btn_layout.addWidget(self._showcase_btn)

        self._open_btn = QPushButton("Open Audio")
        self._open_btn.setMinimumHeight(40)
        self._open_btn.setToolTip("Open your own audio file")
        self._open_btn.clicked.connect(self._on_open_audio)
        btn_layout.addWidget(self._open_btn)

        layout.addLayout(btn_layout)

        layout.addSpacing(8)

        # Don't show again checkbox
        self._dismiss_checkbox = QCheckBox("Don't show this again")
        self._dismiss_checkbox.setChecked(False)
        layout.addWidget(self._dismiss_checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    @property
    def action(self) -> str:
        """The action chosen by the user."""
        return self._action

    def _on_showcase(self) -> None:
        self._action = WelcomeAction.LOAD_SHOWCASE
        self._maybe_dismiss()
        self.accept()

    def _on_open_audio(self) -> None:
        self._action = WelcomeAction.OPEN_AUDIO
        self._maybe_dismiss()
        self.accept()

    def _maybe_dismiss(self) -> None:
        if self._dismiss_checkbox.isChecked():
            _save_dismissed()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Handle dialog close via X button."""
        self._maybe_dismiss()
        super().closeEvent(event)

"""Audio file import dialog."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog


AUDIO_FILTER = (
    "Audio Files (*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma);;"
    "All Files (*)"
)


def _project_dir(subdir: str) -> str:
    """Return the project-level directory for file dialogs, creating it if needed."""
    d = Path(__file__).resolve().parents[3] / subdir
    d.mkdir(exist_ok=True)
    return str(d)


def open_audio_file(parent=None) -> Path | None:
    """Open a file dialog for selecting an audio file.

    Returns the selected path, or None if cancelled.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Import Audio File",
        _project_dir("audio"),
        AUDIO_FILTER,
    )
    if path:
        return Path(path)
    return None

"""Background image/color picker widget."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog


IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"


def open_background_image(parent=None) -> Path | None:
    """Open a file dialog for selecting a background image.

    Returns the selected path, or None if cancelled.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Select Background Image",
        "",
        IMAGE_FILTER,
    )
    if path:
        return Path(path)
    return None

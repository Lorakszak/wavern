"""Fade in/out settings section for the visual settings panel."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.presets.schema import Preset


class FadeSection(QWidget):
    """Editable fade-in and fade-out duration controls."""

    fade_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset: Preset | None = None
        self._rebuilding = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def build(self, preset: Preset) -> None:
        """Build the fade controls from a preset."""
        self._preset = preset
        self._rebuilding = True

        while self._layout.count():
            item = self._layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()

        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(4, 0, 4, 0)

        self._fade_in_spin = DragSpinBox(
            minimum=0.0,
            maximum=30.0,
            step=0.1,
            decimals=1,
            description="Duration of the fade-in from black at the start of the video.",
            default_value=0.0,
        )
        self._fade_in_spin.setValue(preset.fade_in)
        self._fade_in_spin.valueChanged.connect(self._on_fade_changed)
        form.addRow("Fade In (s):", self._fade_in_spin)

        self._fade_out_spin = DragSpinBox(
            minimum=0.0,
            maximum=30.0,
            step=0.1,
            decimals=1,
            description="Duration of the fade-out to black at the end of the video.",
            default_value=0.0,
        )
        self._fade_out_spin.setValue(preset.fade_out)
        self._fade_out_spin.valueChanged.connect(self._on_fade_changed)
        form.addRow("Fade Out (s):", self._fade_out_spin)

        self._layout.addWidget(content)
        self._rebuilding = False

    def update_values(self, preset: Preset) -> None:
        """Sync widget values without rebuilding."""
        self._preset = preset
        self._rebuilding = True
        self._fade_in_spin.setValue(preset.fade_in)
        self._fade_out_spin.setValue(preset.fade_out)
        self._rebuilding = False

    def _on_fade_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.fade_in = self._fade_in_spin.value()
        self._preset.fade_out = self._fade_out_spin.value()
        self.fade_changed.emit()

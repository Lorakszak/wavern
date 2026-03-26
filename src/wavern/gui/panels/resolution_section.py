"""Resolution and frame rate settings section for the project settings panel."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.constants import ASPECT_RATIOS, FPS_OPTIONS, RESOLUTION_PRESETS
from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import ProjectSettings


class ResolutionSection(QWidget):
    """Aspect ratio, resolution presets, dimensions, and FPS controls."""

    resolution_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rebuilding = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        # --- Resolution ---
        separator_res = QLabel("Resolution")
        separator_res.setObjectName("SectionSeparator")
        form.addRow(separator_res)

        # Aspect ratio
        aspect_row = QHBoxLayout()
        self._aspect_combo = NoScrollComboBox()
        self._aspect_combo.addItems(ASPECT_RATIOS)
        self._aspect_combo.setCurrentText("16:9")
        aspect_row.addWidget(self._aspect_combo, stretch=1)
        aspect_row.addWidget(make_help_button(
            "Aspect ratio determines the shape of the output video.\n"
            "Select 'Custom' to enter arbitrary dimensions."
        ))
        form.addRow("Aspect Ratio:", aspect_row)

        # Resolution quick-select
        quick_row = QHBoxLayout()
        self._res_combo = NoScrollComboBox()
        self._populate_resolution_combo("16:9")
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == (1920, 1080):
                self._res_combo.setCurrentIndex(i)
                break
        quick_row.addWidget(self._res_combo, stretch=1)
        quick_row.addWidget(make_help_button(
            "Resolution is the pixel dimensions of the output video.\n"
            "Higher resolution = sharper image but larger file and slower export."
        ))
        form.addRow("Preset:", quick_row)

        # Manual width x height
        dim_row = QHBoxLayout()
        self._width_spin = DragSpinBox(
            minimum=320, maximum=7680, step=1, decimals=0, default_value=1920,
        )
        self._width_spin.setValue(1920)
        dim_row.addWidget(self._width_spin)
        dim_row.addWidget(QLabel("x"))
        self._height_spin = DragSpinBox(
            minimum=240, maximum=4320, step=1, decimals=0, default_value=1080,
        )
        self._height_spin.setValue(1080)
        dim_row.addWidget(self._height_spin)
        form.addRow("Size:", dim_row)

        # --- Frame Rate ---
        separator_fps = QLabel("Frame Rate")
        separator_fps.setObjectName("SectionSeparator")
        form.addRow(separator_fps)

        fps_row = QHBoxLayout()
        self._fps_combo = NoScrollComboBox()
        for fps in FPS_OPTIONS:
            self._fps_combo.addItem(str(fps), fps)
        self._fps_combo.addItem("Custom", -1)
        self._fps_combo.setCurrentIndex(3)  # 60
        fps_row.addWidget(self._fps_combo, stretch=1)
        fps_row.addWidget(make_help_button(
            "Frames per second — how many images are rendered each second.\n"
            "Higher FPS = smoother motion but larger file.\n"
            "24/25 = cinematic, 30 = standard, 60 = smooth, 120 = very smooth."
        ))
        form.addRow("FPS:", fps_row)

        self._fps_spin = DragSpinBox(
            minimum=1, maximum=240, step=1, decimals=0, default_value=60,
        )
        self._fps_spin.setValue(60)
        form.addRow("Value:", self._fps_spin)

        layout.addLayout(form)
        self._connect_signals()

    def _connect_signals(self) -> None:
        self._aspect_combo.currentTextChanged.connect(self._on_aspect_changed)
        self._res_combo.currentIndexChanged.connect(self._on_res_preset_changed)
        self._width_spin.valueChanged.connect(self._on_dimension_changed)
        self._height_spin.valueChanged.connect(self._on_dimension_changed)
        self._fps_combo.currentIndexChanged.connect(self._on_fps_combo_changed)
        self._fps_spin.valueChanged.connect(self._on_fps_spin_changed)

    def collect(self) -> dict:
        """Return current resolution/fps settings as a dict.

        Returns:
            Dict with 'resolution' (tuple[int, int]) and 'fps' (int) keys.
        """
        return {
            "resolution": (int(self._width_spin.value()), int(self._height_spin.value())),
            "fps": int(self._fps_spin.value()),
        }

    def reset(self, defaults: ProjectSettings) -> None:
        """Reset all widgets to default values.

        Args:
            defaults: A ProjectSettings instance with default values.
        """
        self._rebuilding = True
        self._aspect_combo.blockSignals(True)
        self._res_combo.blockSignals(True)
        self._width_spin.blockSignals(True)
        self._height_spin.blockSignals(True)
        self._fps_combo.blockSignals(True)
        self._fps_spin.blockSignals(True)

        self._aspect_combo.setCurrentText("16:9")
        self._populate_resolution_combo("16:9")
        self._res_combo.setEnabled(True)
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == defaults.resolution:
                self._res_combo.setCurrentIndex(i)
                break
        self._width_spin.setValue(defaults.resolution[0])
        self._height_spin.setValue(defaults.resolution[1])
        self._fps_spin.setValue(defaults.fps)
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == defaults.fps:
                self._fps_combo.setCurrentIndex(i)
                break

        self._aspect_combo.blockSignals(False)
        self._res_combo.blockSignals(False)
        self._width_spin.blockSignals(False)
        self._height_spin.blockSignals(False)
        self._fps_combo.blockSignals(False)
        self._fps_spin.blockSignals(False)
        self._rebuilding = False

    def update_values(self, settings: ProjectSettings) -> None:
        """Sync widget state from external settings (dual sidebar sync).

        Args:
            settings: ProjectSettings to sync from.
        """
        self._rebuilding = True
        w, h = settings.resolution

        self._width_spin.blockSignals(True)
        self._height_spin.blockSignals(True)
        self._fps_spin.blockSignals(True)
        self._fps_combo.blockSignals(True)
        self._res_combo.blockSignals(True)

        self._width_spin.setValue(w)
        self._height_spin.setValue(h)
        self._fps_spin.setValue(settings.fps)

        # Sync FPS combo
        match_idx = -1
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == settings.fps:
                match_idx = i
                break
        if match_idx >= 0:
            self._fps_combo.setCurrentIndex(match_idx)
        else:
            custom_idx = self._fps_combo.findData(-1)
            if custom_idx >= 0:
                self._fps_combo.setCurrentIndex(custom_idx)

        # Sync resolution combo
        for i in range(self._res_combo.count()):
            if self._res_combo.itemData(i) == (w, h):
                self._res_combo.setCurrentIndex(i)
                break

        self._width_spin.blockSignals(False)
        self._height_spin.blockSignals(False)
        self._fps_spin.blockSignals(False)
        self._fps_combo.blockSignals(False)
        self._res_combo.blockSignals(False)
        self._rebuilding = False

    # --- Internal callbacks ---

    def _populate_resolution_combo(self, aspect: str) -> None:
        """Populate resolution combo for the given aspect ratio."""
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        presets = RESOLUTION_PRESETS.get(aspect, [])
        for w, h in presets:
            self._res_combo.addItem(f"{w}x{h}", (w, h))
        self._res_combo.blockSignals(False)

    def _on_aspect_changed(self, aspect: str) -> None:
        if aspect == "Custom":
            self._res_combo.setEnabled(False)
            return

        self._res_combo.setEnabled(True)
        self._populate_resolution_combo(aspect)

        if self._res_combo.count() > 0:
            current = (int(self._width_spin.value()), int(self._height_spin.value()))
            best_idx = 0
            for i in range(self._res_combo.count()):
                res = self._res_combo.itemData(i)
                if res == current:
                    best_idx = i
                    break
            self._res_combo.setCurrentIndex(best_idx)
            self._sync_spinboxes_from_combo()

    def _on_res_preset_changed(self, index: int) -> None:
        if index < 0:
            return
        self._sync_spinboxes_from_combo()

    def _sync_spinboxes_from_combo(self) -> None:
        """Update width/height spinboxes from the resolution combo selection."""
        data = self._res_combo.currentData()
        if not isinstance(data, tuple):
            return
        w, h = data
        self._rebuilding = True
        self._width_spin.setValue(w)
        self._height_spin.setValue(h)
        self._rebuilding = False
        self.resolution_changed.emit()

    def _on_dimension_changed(self) -> None:
        if self._rebuilding:
            return
        self._aspect_combo.blockSignals(True)
        self._aspect_combo.setCurrentText("Custom")
        self._aspect_combo.blockSignals(False)
        self._res_combo.setEnabled(False)
        self.resolution_changed.emit()

    def _on_fps_combo_changed(self, index: int) -> None:
        fps_val = self._fps_combo.currentData()
        if isinstance(fps_val, int) and fps_val != -1:
            self._rebuilding = True
            self._fps_spin.setValue(fps_val)
            self._rebuilding = False
        self.resolution_changed.emit()

    def _on_fps_spin_changed(self) -> None:
        if self._rebuilding:
            return
        value = int(self._fps_spin.value())
        match_idx = -1
        for i in range(self._fps_combo.count()):
            if self._fps_combo.itemData(i) == value:
                match_idx = i
                break
        self._fps_combo.blockSignals(True)
        if match_idx >= 0:
            self._fps_combo.setCurrentIndex(match_idx)
        else:
            custom_idx = self._fps_combo.findData(-1)
            if custom_idx >= 0:
                self._fps_combo.setCurrentIndex(custom_idx)
        self._fps_combo.blockSignals(False)
        self.resolution_changed.emit()

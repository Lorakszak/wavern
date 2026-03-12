"""Preset browser panel — list, search, save/load/delete presets."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.presets.manager import PresetError, PresetManager
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


class PresetPanel(QWidget):
    """Preset browser with search, save, load, delete functionality."""

    preset_selected = Signal(object)  # Preset
    preset_saved = Signal(str)  # preset name

    def __init__(self, preset_manager: PresetManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = preset_manager
        self._current_preset: Preset | None = None

        self._setup_ui()
        self.refresh_list()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search presets...")
        self._search_input.textChanged.connect(self._on_search)
        layout.addWidget(self._search_input)

        # Preset list
        self._preset_list = QListWidget()
        self._preset_list.itemClicked.connect(self._on_preset_clicked)
        layout.addWidget(self._preset_list, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()

        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        layout.addLayout(btn_layout)

    def refresh_list(self) -> None:
        """Reload the preset list from disk."""
        self._preset_list.clear()
        search = self._search_input.text().lower()

        for info in self._manager.list_presets():
            name = info["name"]
            if search and search not in name.lower():
                continue

            source = info["source"]
            label = f"{name} ({source})" if source == "builtin" else name
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._preset_list.addItem(item)

    def set_current_preset(self, preset: Preset) -> None:
        """Set the currently active preset (for save operations)."""
        self._current_preset = preset

    def _on_search(self, text: str) -> None:
        self.refresh_list()

    def _on_preset_clicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        try:
            preset = self._manager.load(name)
            self._current_preset = preset
            self.preset_selected.emit(preset)
        except PresetError as e:
            logger.error("Failed to load preset: %s", e)
            QMessageBox.warning(self, "Preset Error", str(e))

    def _on_save(self) -> None:
        if self._current_preset is None:
            QMessageBox.information(self, "Save", "No preset to save.")
            return

        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Preset name:",
            text=self._current_preset.name,
        )
        if not ok or not name:
            return

        self._current_preset.name = name
        try:
            self._manager.save(self._current_preset)
            self.refresh_list()
            self.preset_saved.emit(name)
        except PresetError as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def _on_delete(self) -> None:
        item = self._preset_list.currentItem()
        if item is None:
            return

        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._manager.delete(name)
                self.refresh_list()
            except PresetError as e:
                QMessageBox.warning(self, "Delete Error", str(e))

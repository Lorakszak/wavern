"""Preset browser panel — list, search, save/load/delete presets."""

import logging

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.favorites_store import FavoritesStore
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.manager import PresetError, PresetManager
from wavern.presets.schema import Preset
from wavern.visualizations.registry import VisualizationRegistry

logger = logging.getLogger(__name__)

# Height presets for S / M / L item sizes
_SIZE_HEIGHTS = {"S": 24, "M": 36, "L": 52}
_SIZE_LABELS = list(_SIZE_HEIGHTS.keys())


class PresetPanel(QWidget):
    """Preset browser with search, save, load, delete functionality."""

    preset_selected = Signal(object)  # Preset
    preset_saved = Signal(str)  # preset name

    def __init__(
        self,
        preset_manager: PresetManager,
        favorites_store: FavoritesStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = preset_manager
        self._favorites = favorites_store
        self._current_preset: Preset | None = None
        self._viz_type_filter: str = ""  # "" means "All Types"

        self._setup_ui()
        self._favorites.changed.connect(self.refresh_list)
        self.refresh_list()

    def _setup_ui(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search presets...")
        self._search_input.textChanged.connect(self._on_search)
        layout.addWidget(self._search_input)

        # Filter row: source combo + favorites-only toggle
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)

        self._source_combo = QComboBox()
        self._source_combo.addItems(["All", "Built-in", "User"])
        self._source_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._source_combo, stretch=1)

        self._fav_filter_btn = QPushButton("★")
        self._fav_filter_btn.setObjectName("PresetFavToggle")
        self._fav_filter_btn.setCheckable(True)
        self._fav_filter_btn.setToolTip("Show favorites only")
        self._fav_filter_btn.setFixedSize(28, 28)
        self._fav_filter_btn.clicked.connect(self._on_favorites_filter_toggled)
        filter_row.addWidget(self._fav_filter_btn)

        layout.addLayout(filter_row)

        # Viz type filter row
        viz_row = QHBoxLayout()
        viz_row.setSpacing(4)

        self._viz_combo = NoScrollComboBox()
        self._viz_combo.addItem("All Types", "")
        registry = VisualizationRegistry()
        for viz in sorted(registry.list_all(), key=lambda v: v["display_name"]):
            self._viz_combo.addItem(viz["display_name"], viz["name"])
        self._viz_combo.currentIndexChanged.connect(self._on_viz_filter_changed)
        viz_row.addWidget(self._viz_combo)

        layout.addLayout(viz_row)

        # Restore persisted viz type filter
        settings = QSettings("wavern", "wavern")
        saved_viz_type = settings.value("preset_panel/viz_type_filter", "")
        if saved_viz_type:
            idx = self._viz_combo.findData(saved_viz_type)
            if idx >= 0:
                self._viz_combo.blockSignals(True)
                self._viz_combo.setCurrentIndex(idx)
                self._viz_combo.blockSignals(False)
                self._viz_type_filter = saved_viz_type

        # Size row: S / M / L exclusive toggle buttons
        size_row = QHBoxLayout()
        size_row.setSpacing(2)

        settings = QSettings("wavern", "wavern")
        saved_size = settings.value("preset_item_size", "M")
        if saved_size not in _SIZE_HEIGHTS:
            saved_size = "M"

        self._size_buttons: dict[str, QPushButton] = {}
        for label in _SIZE_LABELS:
            btn = QPushButton(label)
            btn.setObjectName("PresetSizeBtn")
            btn.setCheckable(True)
            btn.setFixedSize(28, 22)
            btn.clicked.connect(lambda checked, lbl=label: self._on_size_changed(lbl))
            size_row.addWidget(btn)
            self._size_buttons[label] = btn

        self._size_buttons[saved_size].setChecked(True)
        self._current_size = saved_size

        size_row.addStretch()
        layout.addLayout(size_row)

        # Preset list
        self._preset_list = QListWidget()
        self._preset_list.itemClicked.connect(self._on_preset_clicked)
        self._preset_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._preset_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._preset_list)

        # Buttons
        btn_layout = QHBoxLayout()

        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        self._rename_btn = QPushButton("Rename")
        self._rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(self._rename_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        self._fav_btn = QPushButton("★")
        self._fav_btn.setObjectName("PresetFavToggle")
        self._fav_btn.setToolTip("Toggle favorite on selected preset")
        self._fav_btn.setFixedSize(28, 28)
        self._fav_btn.clicked.connect(self._on_toggle_favorite)
        btn_layout.addWidget(self._fav_btn)

        layout.addLayout(btn_layout)

    def refresh_list(self) -> None:
        """Reload the preset list from disk, applying all active filters."""
        # Preserve scroll position and selected item across rebuilds
        scrollbar = self._preset_list.verticalScrollBar()
        scroll_value = scrollbar.value() if scrollbar else 0
        current_item = self._preset_list.currentItem()
        selected_name: str | None = (
            current_item.data(Qt.ItemDataRole.UserRole) if current_item else None
        )

        self._preset_list.clear()
        search = self._search_input.text().lower()
        source_filter = self._source_combo.currentText()  # "All", "Built-in", "User"
        fav_only = self._fav_filter_btn.isChecked()
        height = _SIZE_HEIGHTS[self._current_size]

        for info in self._manager.list_presets_with_type():
            name = info["name"]
            source = info["source"]

            # Text filter
            if search and search not in name.lower():
                continue

            # Source filter
            if source_filter == "Built-in" and source != "builtin":
                continue
            if source_filter == "User" and source != "user":
                continue

            # Viz type filter
            if self._viz_type_filter and info["visualization_type"] != self._viz_type_filter:
                continue

            # Favorites filter
            is_fav = self._favorites.is_favorite(name)
            if fav_only and not is_fav:
                continue

            # Build label
            star = "★ " if is_fav else ""
            suffix = f" ({source})" if source == "builtin" else ""
            label = f"{star}{name}{suffix}"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setSizeHint(QSize(0, height))
            self._preset_list.addItem(item)

        # Restore selection
        if selected_name is not None:
            for i in range(self._preset_list.count()):
                it = self._preset_list.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == selected_name:
                    self._preset_list.setCurrentItem(it)
                    break

        # Restore scroll position
        if scrollbar:
            scrollbar.setValue(scroll_value)

    def set_current_preset(self, preset: Preset) -> None:
        """Set the currently active preset (for save operations)."""
        self._current_preset = preset

    # ── Slots ──

    def _on_search(self, text: str) -> None:
        self.refresh_list()

    def _on_filter_changed(self, index: int) -> None:
        self.refresh_list()

    def _on_favorites_filter_toggled(self) -> None:
        self.refresh_list()

    def _on_viz_filter_changed(self) -> None:
        self._viz_type_filter = self._viz_combo.currentData() or ""
        settings = QSettings("wavern", "wavern")
        settings.setValue("preset_panel/viz_type_filter", self._viz_type_filter)
        self.refresh_list()

    def _on_size_changed(self, label: str) -> None:
        # Enforce exclusive toggle manually
        for lbl, btn in self._size_buttons.items():
            btn.setChecked(lbl == label)
        self._current_size = label

        # Persist
        settings = QSettings("wavern", "wavern")
        settings.setValue("preset_item_size", label)

        self.refresh_list()

    def _on_toggle_favorite(self) -> None:
        item = self._preset_list.currentItem()
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._favorites.toggle(name)

    def _on_context_menu(self, pos) -> None:
        item = self._preset_list.itemAt(pos)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        fav_label = "Remove from Favorites" if self._favorites.is_favorite(name) else "Add to Favorites"
        fav_action = menu.addAction(fav_label)
        action = menu.exec(self._preset_list.mapToGlobal(pos))
        if action == fav_action:
            self._favorites.toggle(name)

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

    def _on_rename(self) -> None:
        item = self._preset_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Rename", "Select a preset to rename.")
            return

        old_name = item.data(Qt.ItemDataRole.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Rename Preset", "New name:", text=old_name
        )
        if not ok or not new_name or new_name == old_name:
            return

        try:
            preset = self._manager.load(old_name)
            preset.name = new_name
            self._manager.save(preset)
            self._manager.delete(old_name)
            self.refresh_list()
            if self._current_preset and self._current_preset.name == old_name:
                self._current_preset.name = new_name
        except PresetError as e:
            QMessageBox.warning(self, "Rename Error", str(e))

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

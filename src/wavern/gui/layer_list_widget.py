"""LayerListWidget — multi-layer management panel for the visualization compositor."""

import logging

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import BlendMode, VisualizationLayer

logger = logging.getLogger(__name__)

_MAX_LAYERS = 7
_MIN_LAYERS = 1

_BLEND_MODE_LABELS: list[tuple[str, BlendMode]] = [
    ("Normal", BlendMode.NORMAL),
    ("Additive", BlendMode.ADDITIVE),
    ("Screen", BlendMode.SCREEN),
    ("Multiply", BlendMode.MULTIPLY),
]

_DEFAULT_VIZ_TYPE = "spectrum_bars"

_ROW_STYLE_NORMAL = ""
_ROW_STYLE_SELECTED = "background-color: rgba(0, 120, 212, 60);"



class _LayerRow(QWidget):
    """A single row representing one visualization layer.

    Args:
        layer: Initial layer config to populate this row.
        data_index: Position in the data model (0 = bottom/background).
        parent: Optional parent widget.
    """

    visibility_clicked = Signal(int)  # data_index
    row_clicked = Signal(int)  # data_index — emitted on click anywhere in the row
    name_changed = Signal(int, str)  # data_index, new_name
    blend_changed = Signal(int, str)  # data_index, blend_mode value
    opacity_changed = Signal(int, float)  # data_index, opacity 0.0–1.0
    delete_clicked = Signal(int)  # data_index
    move_up_clicked = Signal(int)  # data_index
    move_down_clicked = Signal(int)  # data_index

    def __init__(
        self,
        layer: VisualizationLayer,
        data_index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_index = data_index
        self._rebuilding = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Eye button — toggle visibility (theme-styled via LayerEyeBtn)
        self._eye_btn = QPushButton()
        self._eye_btn.setObjectName("LayerEyeBtn")
        self._eye_btn.setFixedSize(24, 24)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setChecked(layer.visible)
        self._eye_btn.setToolTip("Toggle visibility")
        self._update_eye_style()
        self._eye_btn.clicked.connect(self._on_visibility_clicked)
        layout.addWidget(self._eye_btn)

        # Editable name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Layer name…")
        self._name_edit.setText(layer.name or layer.visualization_type)
        self._name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name_edit.editingFinished.connect(self._on_name_changed)
        layout.addWidget(self._name_edit)

        # Blend mode dropdown
        self._blend_combo = NoScrollComboBox()
        for label, mode in _BLEND_MODE_LABELS:
            self._blend_combo.addItem(label, userData=mode.value)
        self._set_blend(layer.blend_mode)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        layout.addWidget(self._blend_combo)

        # Opacity DragSpinBox (0–100 %, represents 0.0–1.0)
        self._opacity_spin = DragSpinBox(minimum=0.0, maximum=100.0, step=1.0, decimals=0)
        self._opacity_spin.setFixedWidth(80)
        self._opacity_spin.setValue(round(layer.opacity * 100))
        self._opacity_spin.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self._opacity_spin)

        # Percent label
        layout.addWidget(QLabel("%"))

        # Move up button (visually up = higher data index = closer to foreground)
        self._up_btn = QPushButton("\u25b2")
        self._up_btn.setObjectName("ColorControlBtn")
        self._up_btn.setFixedSize(24, 24)
        self._up_btn.setToolTip("Move layer up (foreground)")
        self._up_btn.clicked.connect(self._on_move_up)
        layout.addWidget(self._up_btn)

        # Move down button (visually down = lower data index = closer to background)
        self._down_btn = QPushButton("\u25bc")
        self._down_btn.setObjectName("ColorControlBtn")
        self._down_btn.setFixedSize(24, 24)
        self._down_btn.setToolTip("Move layer down (background)")
        self._down_btn.clicked.connect(self._on_move_down)
        layout.addWidget(self._down_btn)

        # Delete button
        self._delete_btn = QPushButton("x")
        self._delete_btn.setObjectName("ColorControlBtn")
        self._delete_btn.setFixedSize(24, 24)
        self._delete_btn.setToolTip("Remove layer")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self._delete_btn)

        # Install event filter on all interactive children so clicking
        # anywhere on the row also selects it.
        for child in [
            self._eye_btn,
            self._name_edit,
            self._blend_combo,
            self._opacity_spin,
            self._up_btn,
            self._down_btn,
            self._delete_btn,
        ]:
            child.installEventFilter(self)

    def update_values(self, layer: VisualizationLayer, data_index: int) -> None:
        """Update row widgets in-place without recreating."""
        self._data_index = data_index
        self._rebuilding = True

        self._eye_btn.setChecked(layer.visible)
        self._update_eye_style()

        self._name_edit.blockSignals(True)
        self._name_edit.setText(layer.name or layer.visualization_type)
        self._name_edit.blockSignals(False)

        self._blend_combo.blockSignals(True)
        self._set_blend(layer.blend_mode)
        self._blend_combo.blockSignals(False)

        self._opacity_spin.blockSignals(True)
        self._opacity_spin.setValue(round(layer.opacity * 100))
        self._opacity_spin.blockSignals(False)

        self._rebuilding = False

    # -- Public helpers --

    def set_data_index(self, index: int) -> None:
        """Update which data-model index this row represents."""
        self._data_index = index

    def set_delete_enabled(self, enabled: bool) -> None:
        """Enable or disable the delete button."""
        self._delete_btn.setEnabled(enabled)

    def set_move_up_enabled(self, enabled: bool) -> None:
        """Enable or disable the move-up button."""
        self._up_btn.setEnabled(enabled)

    def set_move_down_enabled(self, enabled: bool) -> None:
        """Enable or disable the move-down button."""
        self._down_btn.setEnabled(enabled)

    def set_selected(self, selected: bool) -> None:
        """Apply or remove selection highlight."""
        self.setStyleSheet(_ROW_STYLE_SELECTED if selected else _ROW_STYLE_NORMAL)

    def _set_blend(self, mode: BlendMode) -> None:
        """Set the blend combo without triggering changed signal."""
        self._rebuilding = True
        for i in range(self._blend_combo.count()):
            if self._blend_combo.itemData(i) == mode.value:
                self._blend_combo.setCurrentIndex(i)
                break
        self._rebuilding = False

    def _update_eye_style(self) -> None:
        """Update eye button text based on visibility state.

        Color is handled by the theme via the LayerEyeBtn object name
        and the :checked pseudo-state.
        """
        self._eye_btn.setText("●" if self._eye_btn.isChecked() else "○")

    # -- Events --

    def mousePressEvent(self, event: object) -> None:
        """Select this row when clicked anywhere on it."""
        self.row_clicked.emit(self._data_index)
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def eventFilter(self, _watched: QObject, event: QEvent) -> bool:
        """Intercept mouse presses on child widgets to also select this row."""
        if event.type() == QEvent.Type.MouseButtonPress:
            self.row_clicked.emit(self._data_index)
        return False

    # -- Slots --

    def _on_visibility_clicked(self) -> None:
        self._update_eye_style()
        self.visibility_clicked.emit(self._data_index)

    def _on_name_changed(self) -> None:
        self.name_changed.emit(self._data_index, self._name_edit.text())

    def _on_blend_changed(self) -> None:
        if self._rebuilding:
            return
        value = self._blend_combo.currentData()
        self.blend_changed.emit(self._data_index, str(value))

    def _on_opacity_changed(self, pct: float) -> None:
        self.opacity_changed.emit(self._data_index, pct / 100.0)

    def _on_delete_clicked(self) -> None:
        self.delete_clicked.emit(self._data_index)

    def _on_move_up(self) -> None:
        self.move_up_clicked.emit(self._data_index)

    def _on_move_down(self) -> None:
        self.move_down_clicked.emit(self._data_index)


class LayerListWidget(QWidget):
    """Widget that manages an ordered list of visualization layers.

    Displays layers in reverse order so the foreground layer (highest data index)
    appears at the top of the list. All public signals and method arguments use
    data-model indices (0 = bottom/background).

    Signals:
        layer_selected: Emitted when a row is selected. Carries the data-model index.
        layer_order_changed: Emitted after layer reorder. Carries (old_index, new_index).
        layer_property_changed: Emitted when blend/opacity/visibility changes.
            Arguments: (data_index, property_name, value).
        layer_added: Emitted after a new layer is appended.
            Carries (data_index, layer_name).
        layer_removed: Emitted after a layer is removed. Carries the removed data-model index.
    """

    layer_selected = Signal(int)
    layer_order_changed = Signal(int, int)  # old_index, new_index
    layer_property_changed = Signal(int, str, object)
    layer_added = Signal(int, str)  # data_index, layer_name
    layer_removed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._layers: list[VisualizationLayer] = []
        self._rows: list[_LayerRow] = []  # index matches data-model index
        self._selected_index: int = -1
        self._next_layer_number: int = 2  # counter for auto-naming new layers

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Rows layout — sized to content, no stretch
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        root.addLayout(self._rows_layout)

        # Add layer button
        self._add_btn = QPushButton("+ Add Layer")
        self._add_btn.clicked.connect(self.add_layer)
        root.addWidget(self._add_btn)

        # Don't stretch vertically — take only the space rows need
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    # -- Public API --

    def build(self, layers: list[VisualizationLayer]) -> None:
        """(Re)build all rows from a list of layer configs.

        Args:
            layers: Ordered layer list, index 0 = bottom/background.
        """
        self._layers = list(layers)
        self._selected_index = -1
        self._next_layer_number = len(layers) + 1
        self._clear_rows()
        for i, layer in enumerate(self._layers):
            self._append_row(layer, i)
        self._refresh_controls()

    def apply(self, layers: list[VisualizationLayer]) -> None:
        """Update layer list with minimal widget churn.

        Reuses existing rows, adds new ones if count increased,
        removes excess if decreased.
        """
        self._layers = list(layers)
        old_count = len(self._rows)
        new_count = len(layers)

        # Update existing rows in-place
        for i in range(min(old_count, new_count)):
            self._rows[i].update_values(layers[i], i)

        # Add new rows if layer count increased
        for i in range(old_count, new_count):
            self._append_row(layers[i], i)

        # Remove excess rows if layer count decreased
        while len(self._rows) > new_count:
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.deleteLater()

        self._refresh_controls()

    def add_layer(self) -> None:
        """Append a new default layer and emit layer_added.

        Does nothing if already at the maximum layer count.
        """
        if not self.can_add_layer():
            logger.debug("add_layer: already at max layers (%d)", _MAX_LAYERS)
            return
        name = f"Layer {self._next_layer_number}"
        self._next_layer_number += 1
        new_layer = VisualizationLayer(visualization_type=_DEFAULT_VIZ_TYPE, name=name)
        new_index = len(self._layers)
        self._layers.append(new_layer)
        self._append_row(new_layer, new_index)
        self._refresh_controls()
        logger.debug("Layer added at index %d: %s", new_index, name)
        self.layer_added.emit(new_index, name)

    def remove_layer(self, index: int) -> None:
        """Remove the layer at *index* and emit layer_removed.

        Args:
            index: Data-model index of the layer to remove (0 = bottom).

        Raises:
            IndexError: If *index* is out of range.
        """
        if not self.can_remove_layer():
            logger.debug("remove_layer: cannot remove — only one layer remains")
            return
        if index < 0 or index >= len(self._layers):
            raise IndexError(f"Layer index {index} out of range [0, {len(self._layers)})")

        self._layers.pop(index)
        self._remove_row(index)
        # Reindex remaining rows
        for i, row in enumerate(self._rows):
            row.set_data_index(i)
        # Adjust selected index
        if self._selected_index == index:
            self._selected_index = -1
        elif self._selected_index > index:
            self._selected_index -= 1
        self._refresh_controls()
        logger.debug("Layer removed at index %d", index)
        self.layer_removed.emit(index)

    def move_layer(self, from_index: int, to_index: int) -> None:
        """Swap the layer at *from_index* with the one at *to_index*.

        Rebuilds row widgets and emits layer_order_changed.

        Args:
            from_index: Data-model index of the layer to move.
            to_index: Data-model index of the destination.
        """
        if from_index == to_index:
            return
        if not (0 <= from_index < len(self._layers) and 0 <= to_index < len(self._layers)):
            logger.warning("move_layer: indices out of range (%d, %d)", from_index, to_index)
            return

        self._layers[from_index], self._layers[to_index] = (
            self._layers[to_index],
            self._layers[from_index],
        )

        # Track selection through the swap
        if self._selected_index == from_index:
            self._selected_index = to_index
        elif self._selected_index == to_index:
            self._selected_index = from_index

        # Rebuild rows to reflect new order
        self._clear_rows()
        for i, layer in enumerate(self._layers):
            self._append_row(layer, i)
        self._refresh_controls()

        # Restore selection highlight
        if 0 <= self._selected_index < len(self._rows):
            self._rows[self._selected_index].set_selected(True)

        logger.debug("Layer moved from %d to %d", from_index, to_index)
        self.layer_order_changed.emit(from_index, to_index)

    def select_layer(self, index: int) -> None:
        """Select the row at *index* and emit layer_selected.

        Args:
            index: Data-model index to select.
        """
        if index < 0 or index >= len(self._layers):
            logger.warning("select_layer: index %d out of range", index)
            return
        old = self._selected_index
        self._selected_index = index
        # Update highlight on old and new row
        if 0 <= old < len(self._rows):
            self._rows[old].set_selected(False)
        self._rows[index].set_selected(True)
        self.layer_selected.emit(index)

    def toggle_visibility(self, index: int) -> None:
        """Toggle the visible flag of the layer at *index*.

        Args:
            index: Data-model index.
        """
        if index < 0 or index >= len(self._layers):
            logger.warning("toggle_visibility: index %d out of range", index)
            return
        current = self._layers[index].visible
        new_visible = not current
        self._layers[index] = self._layers[index].model_copy(update={"visible": new_visible})
        self.layer_property_changed.emit(index, "visible", new_visible)

    def layer_count(self) -> int:
        """Return the current number of layers."""
        return len(self._layers)

    def can_add_layer(self) -> bool:
        """Return True if a new layer can be added (< 7 layers)."""
        return len(self._layers) < _MAX_LAYERS

    def can_remove_layer(self) -> bool:
        """Return True if a layer can be removed (> 1 layer)."""
        return len(self._layers) > _MIN_LAYERS

    def selected_index(self) -> int:
        """Return the currently selected data-model index, or -1 if none."""
        return self._selected_index

    # -- Internal helpers --

    def _clear_rows(self) -> None:
        """Remove all row widgets from the layout and internal list."""
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.setParent(None)  # type: ignore[call-overload]
            row.deleteLater()
        self._rows.clear()

    def _append_row(self, layer: VisualizationLayer, data_index: int) -> None:
        """Create a row widget and insert it at layout position 0 (top).

        Rows are displayed in reverse: the last data index (foreground) at top.

        Args:
            layer: Layer config for the row.
            data_index: Data-model index for this layer.
        """
        row = _LayerRow(layer, data_index)
        row.set_delete_enabled(self.can_remove_layer())

        # Connect signals
        row.row_clicked.connect(self._on_row_clicked)
        row.visibility_clicked.connect(self._on_visibility_clicked)
        row.name_changed.connect(self._on_name_changed)
        row.blend_changed.connect(self._on_blend_changed)
        row.opacity_changed.connect(self._on_opacity_changed)
        row.delete_clicked.connect(self._on_delete_clicked)
        row.move_up_clicked.connect(self._on_move_up_clicked)
        row.move_down_clicked.connect(self._on_move_down_clicked)

        # Insert at top (index 0 in the layout, before the stretch)
        self._rows_layout.insertWidget(0, row)
        self._rows.append(row)

    def _remove_row(self, data_index: int) -> None:
        """Remove the row widget for *data_index* from the layout.

        Args:
            data_index: Data-model index whose row should be removed.
        """
        row = self._rows.pop(data_index)
        self._rows_layout.removeWidget(row)
        row.setParent(None)  # type: ignore[call-overload]
        row.deleteLater()

    def _refresh_controls(self) -> None:
        """Update add button, delete buttons, and move buttons on all rows."""
        self._add_btn.setEnabled(self.can_add_layer())
        can_del = self.can_remove_layer()
        n = len(self._rows)
        for i, row in enumerate(self._rows):
            row.set_delete_enabled(can_del)
            # Highest index is at the top visually, so it cannot move up further
            row.set_move_up_enabled(i < n - 1)
            # Index 0 is already at the bottom, cannot move down
            row.set_move_down_enabled(i > 0)

    # -- Row signal handlers --

    def _on_row_clicked(self, data_index: int) -> None:
        self.select_layer(data_index)

    def _on_visibility_clicked(self, data_index: int) -> None:
        self.toggle_visibility(data_index)

    def _on_name_changed(self, data_index: int, name: str) -> None:
        self._layers[data_index] = self._layers[data_index].model_copy(update={"name": name})
        self.layer_property_changed.emit(data_index, "name", name)

    def _on_blend_changed(self, data_index: int, blend_value: str) -> None:
        mode = BlendMode(blend_value)
        self._layers[data_index] = self._layers[data_index].model_copy(
            update={"blend_mode": mode}
        )
        self.layer_property_changed.emit(data_index, "blend_mode", mode)

    def _on_opacity_changed(self, data_index: int, opacity: float) -> None:
        self._layers[data_index] = self._layers[data_index].model_copy(
            update={"opacity": opacity}
        )
        self.layer_property_changed.emit(data_index, "opacity", opacity)

    def _on_delete_clicked(self, data_index: int) -> None:
        self.remove_layer(data_index)

    def _on_move_up_clicked(self, data_index: int) -> None:
        if data_index < len(self._layers) - 1:
            self.move_layer(data_index, data_index + 1)

    def _on_move_down_clicked(self, data_index: int) -> None:
        if data_index > 0:
            self.move_layer(data_index, data_index - 1)

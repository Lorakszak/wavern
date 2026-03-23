"""DragSpinBox — a custom numeric input with drag-to-change, progress bar, and no scroll hijack."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QSizePolicy, QWidget

from wavern.gui.help_button import make_help_button


class DragSpinBox(QWidget):
    """Numeric input widget with drag-to-change, inline editing, and progress fill.

    Features:
    - Visual: value text drawn over a filled progress bar (fill = (value - min) / (max - min)).
      Min/max labels on the sides. Optional '?' help button. Optional reset-to-default button.
    - Click-to-edit: double-click reveals an inline QLineEdit for keyboard entry.
      Enter/focus-out commits.
    - Drag-to-change: horizontal mouse drag adjusts value.
      delta = mouse_dx * (max - min) / widget_width.
      Shift = fine (0.1x), Ctrl = coarse (10x).
    - No scroll wheel: wheelEvent calls event.ignore() so scrolling passes through
      to the parent QScrollArea.
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        minimum: float = 0.0,
        maximum: float = 100.0,
        step: float = 1.0,
        decimals: int = 0,
        description: str = "",
        default_value: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._step = step
        self._decimals = decimals
        self._description = description
        self._default_value = default_value
        self._value = minimum

        self._dragging = False
        self._drag_start_x: float = 0.0
        self._drag_start_value = 0.0

        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Layout: bar area + optional reset button + optional help button
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # The paintable bar area
        self._bar = _BarArea(self)
        layout.addWidget(self._bar, stretch=1)

        if default_value is not None:
            reset_btn = QPushButton("\u21BA")
            reset_btn.setObjectName("ResetButton")
            reset_btn.setFixedSize(20, 20)
            reset_btn.setToolTip(f"Reset to default ({default_value:g})")
            reset_btn.clicked.connect(lambda: self.setValue(default_value))
            layout.addWidget(reset_btn)

        if description:
            layout.addWidget(make_help_button(description))

        # Inline editor (hidden by default)
        self._editor = QLineEdit(self._bar)
        self._editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor.hide()
        self._editor.editingFinished.connect(self._commit_edit)

    # -- Public API --

    def value(self) -> float:
        return self._value

    def setValue(self, val: float) -> None:
        clamped = max(self._min, min(self._max, val))
        if self._decimals == 0:
            clamped = round(clamped)
        else:
            clamped = round(clamped, self._decimals)
        if clamped != self._value:
            self._value = clamped
            self._bar.update()
            self.valueChanged.emit(self._value)

    def setRange(self, minimum: float, maximum: float) -> None:
        self._min = minimum
        self._max = maximum
        self.setValue(self._value)

    def setDecimals(self, decimals: int) -> None:
        self._decimals = decimals

    def setSingleStep(self, step: float) -> None:
        self._step = step

    def minimum(self) -> float:
        return self._min

    def maximum(self) -> float:
        return self._max

    # -- Wheel --

    def wheelEvent(self, event) -> None:
        event.ignore()

    # -- Formatting --

    def _format_value(self) -> str:
        if self._decimals == 0:
            return str(int(self._value))
        return f"{self._value:.{self._decimals}f}"

    def _fill_ratio(self) -> float:
        span = self._max - self._min
        if span <= 0:
            return 0.0
        return (self._value - self._min) / span

    # -- Inline editor --

    def _begin_edit(self) -> None:
        self._editor.setGeometry(self._bar.rect())
        self._editor.setText(self._format_value())
        self._editor.selectAll()
        self._editor.show()
        self._editor.setFocus()

    def _commit_edit(self) -> None:
        text = self._editor.text().strip()
        self._editor.hide()
        try:
            val = float(text)
            self.setValue(val)
        except ValueError:
            pass


class _BarArea(QWidget):
    """Internal paintable area for the progress bar + value text."""

    def __init__(self, parent: "DragSpinBox") -> None:
        super().__init__(parent)
        self._dsb = parent
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        dsb = self._dsb

        # Background
        bg_color = QColor("#3c3c3c")
        p.fillRect(0, 0, w, h, bg_color)

        # Fill bar
        fill_w = int(w * dsb._fill_ratio())
        if fill_w > 0:
            fill_color = QColor("#0078d4")
            fill_color.setAlpha(120)
            p.fillRect(0, 0, fill_w, h, fill_color)

        # Border
        p.setPen(QColor("#555"))
        p.drawRect(0, 0, w - 1, h - 1)

        # Min label (left)
        p.setPen(QColor("#777"))
        fm = QFontMetrics(p.font())
        if dsb._decimals == 0:
            min_text = str(int(dsb._min))
            max_text = str(int(dsb._max))
        else:
            min_text = f"{dsb._min:g}"
            max_text = f"{dsb._max:g}"
        p.drawText(4, 0, w, h, Qt.AlignmentFlag.AlignVCenter, min_text)
        # Max label (right)
        max_w = fm.horizontalAdvance(max_text)
        p.drawText(w - max_w - 4, 0, max_w + 4, h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, max_text)

        # Value text (center)
        p.setPen(QColor("#ddd"))
        val_text = dsb._format_value()
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, val_text)

        p.end()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._dsb._begin_edit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dsb._dragging = True
            self._dsb._drag_start_x = event.position().x()
            self._dsb._drag_start_value = self._dsb._value
            self.grabMouse()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dsb._dragging:
            return
        dx = event.position().x() - self._dsb._drag_start_x
        span = self._dsb._max - self._dsb._min
        bar_width = self.width() or 1

        sensitivity = span / bar_width
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            sensitivity *= 0.1
        elif mods & Qt.KeyboardModifier.ControlModifier:
            sensitivity *= 10.0

        new_val = self._dsb._drag_start_value + dx * sensitivity
        self._dsb.setValue(new_val)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dsb._dragging:
            self._dsb._dragging = False
            self.releaseMouse()

    def wheelEvent(self, event) -> None:
        event.ignore()

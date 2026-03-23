"""Tests for wavern.gui.drag_spinbox.

WHAT THIS TESTS:
- DragSpinBox value setting, clamping to min/max, and integer rounding
- valueChanged signal emission and suppression when value is unchanged
- setRange() clamps existing value to the new bounds
- wheelEvent is ignored (no value change on scroll)
Does NOT test: mouse drag interaction or keyboard input handling
"""

import pytest

from wavern.gui.drag_spinbox import DragSpinBox


class TestDragSpinBox:
    """Tests for DragSpinBox value handling, clamping, and signal emission."""

    def test_initial_value(self) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        assert dsb.value() == 0

    def test_set_value(self) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(42)
        assert dsb.value() == 42

    def test_clamp_above_max(self) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(200)
        assert dsb.value() == 100

    def test_clamp_below_min(self) -> None:
        dsb = DragSpinBox(minimum=10, maximum=100, step=1, decimals=0)
        dsb.setValue(5)
        assert dsb.value() == 10

    def test_float_decimals(self) -> None:
        dsb = DragSpinBox(minimum=0.0, maximum=1.0, step=0.1, decimals=2)
        dsb.setValue(0.555)
        assert dsb.value() == pytest.approx(0.56, abs=0.001)

    def test_integer_mode(self) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(42.7)
        assert dsb.value() == 43
        assert isinstance(dsb.value(), (int, float))

    def test_signal_emission(self, qtbot) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        with qtbot.waitSignal(dsb.valueChanged, timeout=1000) as blocker:
            dsb.setValue(50)
        assert blocker.args == [50]

    def test_no_signal_on_same_value(self, qtbot) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(50)
        # Setting the same value should not emit
        signals = []
        dsb.valueChanged.connect(lambda v: signals.append(v))
        dsb.setValue(50)
        assert signals == []

    def test_set_range(self) -> None:
        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(80)
        dsb.setRange(0, 50)
        assert dsb.value() == 50  # clamped to new max

    def test_negative_range(self) -> None:
        dsb = DragSpinBox(minimum=-20, maximum=20, step=1, decimals=0)
        dsb.setValue(-10)
        assert dsb.value() == -10

    def test_wheel_event_ignored(self, qtbot) -> None:
        """wheelEvent should call event.ignore() — no value change."""
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QWheelEvent

        dsb = DragSpinBox(minimum=0, maximum=100, step=1, decimals=0)
        dsb.setValue(50)
        event = QWheelEvent(
            QPoint(10, 10), QPoint(10, 10),
            QPoint(0, 120), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        dsb.wheelEvent(event)
        assert dsb.value() == 50

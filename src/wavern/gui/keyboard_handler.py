"""Application-level keyboard event filter for transport and navigation shortcuts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, cast

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit

if TYPE_CHECKING:
    from wavern.core.audio_player import AudioPlayer
    from wavern.gui.transport_bar import TransportBar


class KeyboardHandler(QObject):
    """Event filter for global keyboard shortcuts.

    Handles transport (space, arrows, home), volume (up/down, M),
    fullscreen (F), percentage seek (0-9), and visualization cycling
    (Ctrl+Tab forward, Ctrl+Shift+Tab backward).

    Args:
        player: The audio player for position/volume queries and control.
        transport: The transport bar for UI updates.
        on_seek: Callback to seek to a position.
        on_toggle_fullscreen: Callback to toggle fullscreen mode.
        on_cycle_viz: Callback to cycle to the next visualization type.
        on_cycle_viz_reverse: Callback to cycle to the previous visualization type.
        on_toggle_ambient: Callback to toggle ambient mode.
        parent: Optional parent QObject.
    """

    def __init__(
        self,
        player: AudioPlayer,
        transport: TransportBar,
        on_seek: Callable[[float], None],
        on_toggle_fullscreen: Callable[[], None],
        on_cycle_viz: Callable[[], None] | None = None,
        on_cycle_viz_reverse: Callable[[], None] | None = None,
        on_toggle_ambient: Callable[[], None] | None = None,
        is_ambient_active: Callable[[], bool] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._transport = transport
        self._on_seek = on_seek
        self._on_toggle_fullscreen = on_toggle_fullscreen
        self._on_cycle_viz = on_cycle_viz
        self._on_cycle_viz_reverse = on_cycle_viz_reverse
        self._on_toggle_ambient = on_toggle_ambient
        self._is_ambient_active = is_ambient_active

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Filter key events for transport shortcuts."""
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key_event = cast(QKeyEvent, event)
        key = key_event.key()
        mods = key_event.modifiers()

        focused = QApplication.focusWidget()
        input_focused = isinstance(focused, (QAbstractSpinBox, QLineEdit))

        # Space → play/pause (skip when typing in a text field)
        if key == Qt.Key.Key_Space:
            if isinstance(focused, QLineEdit):
                return super().eventFilter(obj, event)
            if self._player.is_playing:
                self._transport.pause_clicked.emit()
            else:
                self._transport.play_clicked.emit()
            return True

        if input_focused:
            return super().eventFilter(obj, event)

        # Home → go to start
        if key == Qt.Key.Key_Home:
            self._on_seek(0.0)
            self._transport.update_position(0.0)
            return True

        # Left / vim-h → seek backward (plain or Shift only, not Ctrl+H)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_H) and not mods & Qt.KeyboardModifier.ControlModifier:
            step = 1.0 if mods & Qt.KeyboardModifier.ShiftModifier else 5.0
            pos = max(0.0, self._player.get_position() - step)
            self._on_seek(pos)
            self._transport.update_position(pos)
            return True

        # Right / vim-l → seek forward
        if key in (Qt.Key.Key_Right, Qt.Key.Key_L):
            step = 1.0 if mods & Qt.KeyboardModifier.ShiftModifier else 5.0
            duration = self._player.duration
            pos = self._player.get_position() + step
            if duration > 0:
                pos = min(duration, pos)
            self._on_seek(pos)
            self._transport.update_position(pos)
            return True

        # M → mute / unmute
        if key == Qt.Key.Key_M:
            self._player.muted = not self._player.muted
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Ctrl+Up → volume +25% (unmutes if muted)
        if key == Qt.Key.Key_Up and mods & Qt.KeyboardModifier.ControlModifier:
            self._player.muted = False
            self._player.volume = self._player.volume + 0.25
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Ctrl+Down → volume -25% (unmutes if muted)
        if key == Qt.Key.Key_Down and mods & Qt.KeyboardModifier.ControlModifier:
            self._player.muted = False
            self._player.volume = self._player.volume - 0.25
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Up → volume +5% (unmutes if muted)
        if key == Qt.Key.Key_Up:
            self._player.muted = False
            self._player.volume = self._player.volume + 0.05
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Down → volume -5% (unmutes if muted)
        if key == Qt.Key.Key_Down:
            self._player.muted = False
            self._player.volume = self._player.volume - 0.05
            self._transport.set_volume(self._player.volume, self._player.muted)
            return True

        # Ctrl+Shift+Tab → cycle to previous visualization type
        # Qt sends Key_Backtab (not Key_Tab) when Shift is held
        if key == Qt.Key.Key_Backtab and mods & Qt.KeyboardModifier.ControlModifier:
            if self._on_cycle_viz_reverse is not None:
                self._on_cycle_viz_reverse()
            return True

        # Ctrl+Tab → cycle to next visualization type
        if key == Qt.Key.Key_Tab and mods & Qt.KeyboardModifier.ControlModifier:
            if self._on_cycle_viz is not None:
                self._on_cycle_viz()
            return True

        # F → toggle fullscreen (same as F11)
        if key == Qt.Key.Key_F:
            self._on_toggle_fullscreen()
            return True

        # Ctrl+H → toggle ambient mode
        if key == Qt.Key.Key_H and mods & Qt.KeyboardModifier.ControlModifier:
            if self._on_toggle_ambient is not None:
                self._on_toggle_ambient()
            return True

        # Escape → exit ambient mode
        if key == Qt.Key.Key_Escape:
            if self._is_ambient_active is not None and self._is_ambient_active():
                if self._on_toggle_ambient is not None:
                    self._on_toggle_ambient()
                return True

        # 0–9 → seek to 0%, 10%, 20%, … 90% of duration
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9 and not mods:
            duration = self._player.duration
            if duration > 0:
                fraction = (key - Qt.Key.Key_0) / 10.0
                pos = duration * fraction
                self._on_seek(pos)
                self._transport.update_position(pos)
            return True

        return super().eventFilter(obj, event)

"""Transport bar — play/pause/seek controls and time display."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyleOptionSlider,
    QStyle,
    QWidget,
)


class _ClickableSlider(QSlider):
    """QSlider that jumps to the clicked position instead of page-stepping."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt,
                QStyle.SubControl.SC_SliderGroove, self,
            )
            if self.orientation() == Qt.Orientation.Horizontal:
                pos = event.position().x()
                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(pos - groove.x()), groove.width(),
                )
            else:
                pos = event.position().y()
                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(pos - groove.y()), groove.height(),
                    upsideDown=True,
                )
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
        super().mousePressEvent(event)


def _format_time(seconds: float) -> str:
    """Format seconds as M:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


class TransportBar(QWidget):
    """Play/pause/seek controls with time display."""

    play_clicked = Signal()
    pause_clicked = Signal()
    seek_requested = Signal(float)  # timestamp in seconds
    loop_toggled = Signal(bool)  # True when loop is enabled

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._duration: float = 0.0
        self._seeking: bool = False

        self._setup_ui()
        self.set_volume(1.0, False)

    @property
    def loop_enabled(self) -> bool:
        """Whether loop playback is active."""
        return self._loop_btn.isChecked()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Play/pause button
        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedWidth(70)
        self._play_btn.clicked.connect(self._on_play_clicked)
        layout.addWidget(self._play_btn)

        # Current time label
        self._time_label = QLabel("0:00")
        self._time_label.setFixedWidth(45)
        layout.addWidget(self._time_label)

        # Seek slider
        self._seek_slider = _ClickableSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 10000)
        self._seek_slider.setValue(0)
        self._seek_slider.sliderPressed.connect(self._on_seek_start)
        self._seek_slider.sliderReleased.connect(self._on_seek_end)
        self._seek_slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._seek_slider, stretch=1)

        # Duration label
        self._duration_label = QLabel("0:00")
        self._duration_label.setFixedWidth(45)
        layout.addWidget(self._duration_label)

        # Loop toggle button
        self._loop_btn = QPushButton("Loop")
        self._loop_btn.setObjectName("LoopButton")
        self._loop_btn.setCheckable(True)
        self._loop_btn.setFixedWidth(60)
        self._loop_btn.setToolTip("Loop playback")
        self._loop_btn.toggled.connect(self.loop_toggled)
        layout.addWidget(self._loop_btn)

        # Volume indicator
        self._volume_label = QLabel("Vol: 100%")
        self._volume_label.setFixedWidth(75)
        self._volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._volume_label)

    def set_duration(self, duration: float) -> None:
        """Set the total duration in seconds."""
        self._duration = duration
        self._duration_label.setText(_format_time(duration))

    def update_position(self, timestamp: float) -> None:
        """Update the displayed position (called from render loop)."""
        if self._seeking:
            return
        self._time_label.setText(_format_time(timestamp))
        if self._duration > 0:
            value = int((timestamp / self._duration) * 10000)
            self._seek_slider.setValue(value)

    def set_volume(self, volume: float, muted: bool) -> None:
        """Update the volume indicator label."""
        display_pct = 0 if muted else int(round(volume * 100))
        self._volume_label.setText(f"Vol: {display_pct}%")

    def set_playing(self, playing: bool) -> None:
        """Update button text based on playback state."""
        self._play_btn.setText("Pause" if playing else "Play")

    def _on_play_clicked(self) -> None:
        if self._play_btn.text() == "Play":
            self.play_clicked.emit()
        else:
            self.pause_clicked.emit()

    def _on_seek_start(self) -> None:
        self._seeking = True

    def _on_seek_end(self) -> None:
        self._seeking = False
        value = self._seek_slider.value()
        timestamp = (value / 10000.0) * self._duration
        self.seek_requested.emit(timestamp)

    def _on_slider_moved(self, value: int) -> None:
        timestamp = (value / 10000.0) * self._duration
        self._time_label.setText(_format_time(timestamp))

    def set_overlay_style(self, enabled: bool) -> None:
        """Toggle semi-transparent overlay appearance for ambient mode."""
        if enabled:
            if not hasattr(self, "_saved_stylesheet"):
                self._saved_stylesheet = self.styleSheet()
            self.setStyleSheet(
                "TransportBar {"
                "  background-color: rgba(0, 0, 0, 0.7);"
                "  border-top: 1px solid rgba(255, 255, 255, 0.1);"
                "}"
            )
        else:
            self.setStyleSheet(getattr(self, "_saved_stylesheet", ""))
            if hasattr(self, "_saved_stylesheet"):
                del self._saved_stylesheet

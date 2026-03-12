"""OpenGL widget for real-time visualization preview."""

import logging

import moderngl
from PySide6.QtCore import QTimer, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from wavern.core.audio_analyzer import AudioAnalyzer, FrameAnalysis
from wavern.core.audio_player import AudioPlayer
from wavern.core.renderer import Renderer
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


class GLPreviewWidget(QOpenGLWidget):
    """OpenGL widget for real-time visualization preview.

    Creates a moderngl context from Qt's OpenGL context and shares it
    with the Renderer. Drives the render loop via a QTimer.
    """

    frame_rendered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ctx: moderngl.Context | None = None
        self._renderer: Renderer | None = None
        self._timer: QTimer | None = None
        self._analyzer: AudioAnalyzer | None = None
        self._player: AudioPlayer | None = None
        self._preset: Preset | None = None
        self._target_fps: int = 60

    def set_analyzer(self, analyzer: AudioAnalyzer) -> None:
        self._analyzer = analyzer

    def set_player(self, player: AudioPlayer) -> None:
        self._player = player

    def set_preset(self, preset: Preset) -> None:
        self._preset = preset
        self._target_fps = preset.fps
        if self._renderer is not None:
            self._renderer.set_preset(preset)
        if self._timer is not None:
            self._timer.setInterval(int(1000 / self._target_fps))

    def update_preset(self, preset: Preset) -> None:
        """Update parameters without full reload."""
        self._preset = preset
        if self._renderer is not None:
            self._renderer.update_params(preset)

    def initializeGL(self) -> None:
        """Called by Qt when the OpenGL context is ready."""
        try:
            self._ctx = moderngl.create_context()
            self._renderer = Renderer(self._ctx)

            if self._preset is not None:
                self._renderer.set_preset(self._preset)

            # Start render timer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.update)
            self._timer.setInterval(int(1000 / self._target_fps))

            logger.info("GL context initialized")
        except Exception as e:
            logger.error("Failed to initialize GL context: %s", e)

    def paintGL(self) -> None:
        """Called every frame — analyze audio and render."""
        if self._renderer is None or self._ctx is None:
            return

        if self._analyzer is None or self._player is None:
            # Render a default empty frame
            resolution = (self.width(), self.height())
            fbo = self._ctx.detect_framebuffer()
            self._ctx.clear(0.05, 0.05, 0.08, 1.0)
            return

        timestamp = self._player.get_position()
        frame = self._analyzer.analyze_frame(timestamp)

        resolution = (self.width(), self.height())
        fbo = self._ctx.detect_framebuffer()
        self._renderer.render_frame(frame, fbo, resolution)

        self.frame_rendered.emit()

    def resizeGL(self, w: int, h: int) -> None:
        """Handle widget resize."""
        if self._ctx is not None:
            self._ctx.viewport = (0, 0, w, h)

    def start_preview(self) -> None:
        """Start the render timer."""
        if self._timer is not None:
            self._timer.start()

    def stop_preview(self) -> None:
        """Stop the render timer."""
        if self._timer is not None:
            self._timer.stop()

    def cleanup(self) -> None:
        """Release GPU resources."""
        self.stop_preview()
        if self._renderer is not None:
            self._renderer.cleanup()

"""OpenGL widget for real-time visualization preview."""

import logging

import numpy as np
import moderngl
from PySide6.QtCore import QTimer, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_player import AudioPlayer
from wavern.core.renderer import Renderer
from wavern.presets.schema import Preset
from wavern.shaders import load_shader

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
        self._checker_program: moderngl.Program | None = None
        self._checker_vao: moderngl.VertexArray | None = None

    def set_analyzer(self, analyzer: AudioAnalyzer) -> None:
        self._analyzer = analyzer

    def set_player(self, player: AudioPlayer) -> None:
        self._player = player

    def set_preset(self, preset: Preset) -> None:
        self._preset = preset
        self._target_fps = preset.fps
        if self._renderer is not None:
            self.makeCurrent()
            self._renderer.set_preset(preset)
            self.doneCurrent()
        if self._timer is not None:
            self._timer.setInterval(int(1000 / self._target_fps))

    def update_preset(self, preset: Preset) -> None:
        """Update parameters without full reload."""
        self._preset = preset
        if self._renderer is not None:
            self.makeCurrent()
            self._renderer.update_params(preset)
            self.doneCurrent()

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

        if self._preset and self._preset.background.type == "none":
            self._render_checkerboard(fbo, resolution)

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

    def _ensure_checker_quad(self) -> None:
        """Lazily compile the checkerboard shader and build the fullscreen quad VAO."""
        if self._checker_program is not None:
            return

        vert_src = load_shader("common.vert")
        frag_src = load_shader("checkerboard.frag")
        self._checker_program = self._ctx.program(
            vertex_shader=vert_src, fragment_shader=frag_src
        )

        vertices = np.array(
            [
                # x,    y,   u,   v
                -1.0, -1.0, 0.0, 0.0,
                 1.0, -1.0, 1.0, 0.0,
                -1.0,  1.0, 0.0, 1.0,
                 1.0,  1.0, 1.0, 1.0,
            ],
            dtype="f4",
        )
        vbo = self._ctx.buffer(vertices.tobytes())
        self._checker_vao = self._ctx.vertex_array(
            self._checker_program,
            [(vbo, "2f 2f", "in_position", "in_texcoord")],
        )

    def _render_checkerboard(self, fbo: moderngl.Framebuffer, resolution: tuple[int, int]) -> None:
        """Render a checkerboard pattern behind existing pixels using destination-over blending.

        Destination-over: checker appears where dst alpha=0 (transparent), visualization
        pixels (dst alpha>0) win. This keeps the checker behind the visualization without
        clearing the framebuffer.
        """
        self._ensure_checker_quad()
        fbo.use()
        self._ctx.viewport = (0, 0, resolution[0], resolution[1])
        # Destination-over blend: src_factor=ONE_MINUS_DST_ALPHA, dst_factor=ONE
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = (moderngl.ONE_MINUS_DST_ALPHA, moderngl.ONE)
        # Tile size in UV space: ~0.04 gives ~20px tiles on a 500px canvas
        tile_size = 0.04
        if "u_tile_size" in self._checker_program:
            self._checker_program["u_tile_size"].value = tile_size
        self._checker_vao.render(moderngl.TRIANGLE_STRIP)
        # Restore standard blend state — renderer relies on BLEND staying enabled
        # across frames (it only enables it, never disables). Using dest-over above
        # would leave the wrong blend_func if we don't restore it here.
        self._ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

    def cleanup(self) -> None:
        """Release GPU resources."""
        self.stop_preview()
        if self._checker_vao is not None:
            self._checker_vao.release()
            self._checker_vao = None
        if self._checker_program is not None:
            self._checker_program.release()
            self._checker_program = None
        if self._renderer is not None:
            self._renderer.cleanup()

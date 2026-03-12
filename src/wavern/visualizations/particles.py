"""Particle system visualization — audio-reactive particle bursts."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register


@register
class ParticlesVisualization(AbstractVisualization):
    """Audio-reactive particle system with burst effects."""

    NAME: ClassVar[str] = "particles"
    DISPLAY_NAME: ClassVar[str] = "Particle Burst"
    DESCRIPTION: ClassVar[str] = "Particles that burst and flow with the music"
    CATEGORY: ClassVar[str] = "particle"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "max_particles": {
            "type": "int", "default": 2000, "min": 100, "max": 10000,
            "label": "Max Particles",
        },
        "particle_size": {
            "type": "float", "default": 4.0, "min": 1.0, "max": 20.0,
            "label": "Particle Size",
        },
        "spawn_rate": {
            "type": "float", "default": 1.0, "min": 0.1, "max": 5.0,
            "label": "Spawn Rate",
        },
        "lifetime": {
            "type": "float", "default": 2.0, "min": 0.5, "max": 10.0,
            "label": "Lifetime (seconds)",
        },
        "spread": {
            "type": "float", "default": 0.5, "min": 0.1, "max": 2.0,
            "label": "Spread",
        },
        "gravity_y": {
            "type": "float", "default": -0.1, "min": -1.0, "max": 1.0,
            "label": "Gravity Y",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None

        max_p = self.get_param("max_particles", 2000)
        # Particle data: x, y, vx, vy, age, lifetime, size, r, g, b, alpha
        self._particles = np.zeros((max_p, 11), dtype="f4")
        self._active_count = 0
        self._last_time = 0.0

    def initialize(self) -> None:
        vert_src = load_shader("particles.vert")
        frag_src = load_shader("particles.frag")

        self._program = self.ctx.program(
            vertex_shader=vert_src,
            fragment_shader=frag_src,
        )

        max_p = self.get_param("max_particles", 2000)
        # VBO: position(2) + size(1) + color(3) + alpha(1) = 7 floats per particle
        self._vbo = self.ctx.buffer(reserve=max_p * 7 * 4)
        self._vao = self.ctx.vertex_array(
            self._program,
            [(self._vbo, "2f 1f 3f 1f", "in_position", "in_size", "in_color", "in_alpha")],
        )

    def render(
        self,
        frame: FrameAnalysis,
        fbo: moderngl.Framebuffer,
        resolution: tuple[int, int],
    ) -> None:
        if self._program is None or self._vao is None or self._vbo is None:
            return

        dt = frame.timestamp - self._last_time
        if dt <= 0 or dt > 0.5:
            dt = 1.0 / 60.0
        self._last_time = frame.timestamp

        self._update_particles(dt, frame)
        self._spawn_particles(frame)

        if self._active_count == 0:
            return

        fbo.use()
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE | moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

        # Build VBO data from active particles
        active = self._particles[: self._active_count]
        vbo_data = np.zeros((self._active_count, 7), dtype="f4")
        vbo_data[:, 0] = active[:, 0]   # x
        vbo_data[:, 1] = active[:, 1]   # y
        vbo_data[:, 2] = active[:, 6]   # size
        vbo_data[:, 3] = active[:, 7]   # r
        vbo_data[:, 4] = active[:, 8]   # g
        vbo_data[:, 5] = active[:, 9]   # b
        vbo_data[:, 6] = active[:, 10]  # alpha

        self._vbo.write(vbo_data.tobytes())

        if "u_resolution" in self._program:
            self._program["u_resolution"].value = resolution
        self._vao.render(moderngl.POINTS, vertices=self._active_count)

        self.ctx.disable(moderngl.PROGRAM_POINT_SIZE | moderngl.BLEND)

    def _update_particles(self, dt: float, frame: FrameAnalysis) -> None:
        """Update particle positions, velocities, and ages."""
        if self._active_count == 0:
            return

        gravity_y = self.get_param("gravity_y", -0.1)
        active = self._particles[: self._active_count]

        # Update velocity (gravity)
        active[:, 3] += gravity_y * dt

        # Update position
        active[:, 0] += active[:, 2] * dt  # x += vx * dt
        active[:, 1] += active[:, 3] * dt  # y += vy * dt

        # Update age
        active[:, 4] += dt

        # Update alpha (fade out)
        lifetime = active[:, 5]
        age_ratio = active[:, 4] / np.maximum(lifetime, 0.01)
        active[:, 10] = np.clip(1.0 - age_ratio, 0.0, 1.0)

        # Remove dead particles (age > lifetime or out of bounds)
        alive_mask = (active[:, 4] < active[:, 5]) & \
                     (active[:, 0] > -0.5) & (active[:, 0] < 1.5) & \
                     (active[:, 1] > -0.5) & (active[:, 1] < 1.5)

        alive_count = int(np.sum(alive_mask))
        if alive_count < self._active_count:
            self._particles[:alive_count] = active[alive_mask]
            self._active_count = alive_count

    def _spawn_particles(self, frame: FrameAnalysis) -> None:
        """Spawn new particles based on audio energy."""
        max_p = self.get_param("max_particles", 2000)
        spawn_rate = self.get_param("spawn_rate", 1.0)
        lifetime = self.get_param("lifetime", 2.0)
        spread = self.get_param("spread", 0.5)
        particle_size = self.get_param("particle_size", 4.0)

        # Spawn count based on amplitude and beat
        base_spawn = int(frame.amplitude * 20 * spawn_rate)
        if frame.beat:
            base_spawn *= 3

        spawn_count = min(base_spawn, max_p - self._active_count)
        if spawn_count <= 0:
            return

        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67)])

        start = self._active_count
        end = start + spawn_count

        for i in range(start, end):
            color = colors[np.random.randint(0, len(colors))]
            angle = np.random.uniform(0, 2 * np.pi)
            speed = np.random.uniform(0.05, 0.3) * spread * (1.0 + frame.amplitude)

            self._particles[i] = [
                0.5,                                    # x (center)
                0.5,                                    # y (center)
                np.cos(angle) * speed,                  # vx
                np.sin(angle) * speed,                  # vy
                0.0,                                    # age
                lifetime * np.random.uniform(0.5, 1.5), # lifetime
                particle_size * np.random.uniform(0.5, 1.5),  # size
                color[0], color[1], color[2],           # rgb
                1.0,                                    # alpha
            ]

        self._active_count = end

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

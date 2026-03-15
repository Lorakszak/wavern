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
            "description": "Maximum number of particles alive at once.",
        },
        "particle_size": {
            "type": "float", "default": 4.0, "min": 0.5, "max": 100.0,
            "label": "Particle Size",
            "description": "Base size of each particle in pixels.",
        },
        "spawn_rate": {
            "type": "float", "default": 1.0, "min": 0.01, "max": 20.0,
            "label": "Spawn Rate",
            "description": "Particle spawn multiplier. Higher = more particles per beat.",
        },
        "lifetime": {
            "type": "float", "default": 2.0, "min": 0.1, "max": 30.0,
            "label": "Lifetime (seconds)",
            "description": "How long each particle lives before fading out.",
        },
        "spread": {
            "type": "float", "default": 0.5, "min": 0.01, "max": 5.0,
            "label": "Spread",
            "description": "How far particles spread from the spawn point.",
        },
        "gravity_y": {
            "type": "float", "default": -0.1, "min": -5.0, "max": 5.0,
            "label": "Gravity Y",
            "description": "Vertical gravity force. Negative = downward, positive = upward.",
        },
        "spawn_x": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 1.0,
            "label": "Spawn X",
            "description": "Horizontal spawn position (0=left, 0.5=center, 1=right).",
        },
        "spawn_y": {
            "type": "float", "default": 0.5, "min": 0.0, "max": 1.0,
            "label": "Spawn Y",
            "description": "Vertical spawn position (0=bottom, 0.5=center, 1=top).",
        },
        "gravity_x": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Gravity X",
            "description": "Horizontal gravity force. Negative = left, positive = right.",
        },
        "speed_min": {
            "type": "float", "default": 0.05, "min": 0.01, "max": 0.5,
            "label": "Min Speed",
            "description": "Minimum initial particle speed.",
        },
        "speed_max": {
            "type": "float", "default": 0.3, "min": 0.1, "max": 1.0,
            "label": "Max Speed",
            "description": "Maximum initial particle speed.",
        },
        "drag": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 0.99,
            "label": "Drag",
            "description": "Velocity damping per frame. Higher = particles slow down faster.",
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
        gravity_x = self.get_param("gravity_x", 0.0)
        active[:, 2] += gravity_x * dt

        # Update position
        active[:, 0] += active[:, 2] * dt  # x += vx * dt
        active[:, 1] += active[:, 3] * dt  # y += vy * dt

        # Apply drag
        drag = self.get_param("drag", 0.0)
        if drag > 0.0:
            drag_factor = 1.0 - drag
            active[:, 2] *= drag_factor  # vx
            active[:, 3] *= drag_factor  # vy

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

        # Spawn count based on amplitude and beat — ensure a minimum trickle
        base_spawn = max(1, int(frame.amplitude * 50 * spawn_rate))
        if frame.beat:
            base_spawn = int(base_spawn * (1.0 + 2.0 * frame.beat_intensity))

        spawn_count = min(base_spawn, max_p - self._active_count)
        if spawn_count <= 0:
            return

        spawn_x = self.get_param("spawn_x", 0.5)
        spawn_y = self.get_param("spawn_y", 0.5)
        speed_min = self.get_param("speed_min", 0.05)
        speed_max = self.get_param("speed_max", 0.3)

        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67)])
        colors_arr = np.array(colors, dtype="f4")

        start = self._active_count
        end = start + spawn_count
        n = spawn_count

        # Vectorized spawn
        angles = np.random.uniform(0, 2 * np.pi, n).astype("f4")
        speeds = (
            np.random.uniform(speed_min, speed_max, n).astype("f4")
            * spread * (1.0 + frame.amplitude)
        )
        color_indices = np.random.randint(0, len(colors_arr), n)

        batch = self._particles[start:end]
        batch[:, 0] = spawn_x
        batch[:, 1] = spawn_y
        batch[:, 2] = np.cos(angles) * speeds
        batch[:, 3] = np.sin(angles) * speeds
        batch[:, 4] = 0.0
        batch[:, 5] = lifetime * np.random.uniform(0.5, 1.5, n).astype("f4")
        batch[:, 6] = particle_size * np.random.uniform(0.5, 1.5, n).astype("f4")
        batch[:, 7:10] = colors_arr[color_indices]
        batch[:, 10] = 1.0

        self._active_count = end

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

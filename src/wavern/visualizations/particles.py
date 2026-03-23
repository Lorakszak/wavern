"""Particle system visualization — audio-reactive particle bursts."""

from typing import Any, ClassVar

import numpy as np
import moderngl

from wavern.core.audio_analyzer import FrameAnalysis
from wavern.presets.schema import VisualizationParams
from wavern.shaders import load_shader
from wavern.visualizations.base import AbstractVisualization
from wavern.visualizations.registry import register

# Particle array columns:
# x(0) y(1) vx(2) vy(3) age(4) lifetime(5) base_size(6)
# r(7) g(8) b(9) alpha(10) color_idx(11)
_COL_COUNT = 12
_X, _Y, _VX, _VY, _AGE, _LIFE, _BSIZE = 0, 1, 2, 3, 4, 5, 6
_R, _G, _B, _ALPHA, _CIDX = 7, 8, 9, 10, 11


def _simple_noise(x: np.ndarray, y: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    """Cheap sin-based turbulence — returns (dx, dy) offset vectors."""
    nx = np.sin(x * 7.3 + t * 2.1) * np.cos(y * 5.7 + t * 1.3)
    ny = np.cos(x * 6.1 + t * 1.7) * np.sin(y * 8.3 + t * 2.9)
    return nx.astype("f4"), ny.astype("f4")


@register
class ParticlesVisualization(AbstractVisualization):
    """Audio-reactive particle system with burst effects."""

    NAME: ClassVar[str] = "particles"
    DISPLAY_NAME: ClassVar[str] = "Particle Burst"
    DESCRIPTION: ClassVar[str] = "Particles that burst and flow with the music"
    CATEGORY: ClassVar[str] = "particle"

    PARAM_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        # --- Core ---
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
        # --- Spawn ---
        "spawn_mode": {
            "type": "choice", "default": "point",
            "choices": ["point", "line", "circle", "edges", "random"],
            "label": "Spawn Mode",
            "description": "Where particles originate: point, line, circle, edges, or random.",
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
        "spawn_radius": {
            "type": "float", "default": 0.3, "min": 0.01, "max": 1.0,
            "label": "Spawn Radius",
            "description": "Radius for circle spawn mode.",
        },
        # --- Physics ---
        "gravity_x": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Gravity X",
            "description": "Horizontal gravity force. Negative = left, positive = right.",
        },
        "gravity_y": {
            "type": "float", "default": -0.1, "min": -5.0, "max": 5.0,
            "label": "Gravity Y",
            "description": "Vertical gravity force. Negative = downward, positive = upward.",
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
        # --- Motion forces ---
        "turbulence": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 1.0,
            "label": "Turbulence",
            "description": "Organic noise-driven velocity perturbation.",
        },
        "radial_force": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Radial Force",
            "description": "Attraction (negative) or repulsion (positive) toward/from spawn point.",
        },
        "vortex": {
            "type": "float", "default": 0.0, "min": -1.0, "max": 1.0,
            "label": "Vortex",
            "description": "Rotational force around spawn point. Creates spiral motion.",
        },
        # --- Audio reactivity ---
        "size_reactivity": {
            "type": "float", "default": 0.3, "min": 0.0, "max": 1.0,
            "label": "Size Reactivity",
            "description": "How much bass energy inflates particle size.",
        },
        "speed_reactivity": {
            "type": "float", "default": 0.3, "min": 0.0, "max": 1.0,
            "label": "Speed Reactivity",
            "description": "How much mid-frequency energy boosts initial speed.",
        },
        "color_shift_reactivity": {
            "type": "float", "default": 0.0, "min": 0.0, "max": 1.0,
            "label": "Color Shift",
            "description": "Shift color palette selection based on frequency spectrum.",
        },
        # --- Lifecycle ---
        "size_over_life": {
            "type": "choice", "default": "constant",
            "choices": ["constant", "grow", "shrink", "pulse"],
            "label": "Size Over Life",
            "description": "How particle size changes over its lifetime.",
        },
        "fade_curve": {
            "type": "choice", "default": "linear",
            "choices": ["linear", "ease_out", "flash"],
            "label": "Fade Curve",
            "description": "Alpha fade shape: linear, ease_out (slow then quick), flash (hold then drop).",
        },
        "color_over_life": {
            "type": "bool", "default": False,
            "label": "Color Over Life",
            "description": "Shift particle color through the palette over its lifetime.",
        },
    }

    def __init__(self, ctx: moderngl.Context, params: VisualizationParams) -> None:
        super().__init__(ctx, params)
        self._program: moderngl.Program | None = None
        self._vao: moderngl.VertexArray | None = None
        self._vbo: moderngl.Buffer | None = None

        max_p = self.get_param("max_particles", 2000)
        self._particles = np.zeros((max_p, _COL_COUNT), dtype="f4")
        self._active_count = 0
        self._last_time = 0.0
        self._time = 0.0

    def update_params(self, params: VisualizationParams) -> None:
        """Reallocate particle array and VBO when max_particles changes."""
        old_max = len(self._particles)
        super().update_params(params)
        new_max = self.get_param("max_particles", 2000)

        if new_max != old_max:
            old_particles = self._particles
            self._particles = np.zeros((new_max, _COL_COUNT), dtype="f4")
            keep = min(self._active_count, new_max)
            self._particles[:keep] = old_particles[:keep]
            self._active_count = keep

            if self._vbo is not None:
                self._vbo.release()
                self._vbo = self.ctx.buffer(reserve=new_max * 7 * 4)
            if self._vao is not None and self._program is not None and self._vbo is not None:
                self._vao.release()
                self._vao = self.ctx.vertex_array(
                    self._program,
                    [(self._vbo, "2f 1f 3f 1f",
                      "in_position", "in_size", "in_color", "in_alpha")],
                )

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
        self._time += dt

        self._update_particles(dt, frame)
        self._spawn_particles(frame)

        if self._active_count == 0:
            return

        fbo.use()
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE | moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)

        # Build VBO data — apply lifecycle transforms
        active = self._particles[: self._active_count]
        vbo_data = np.zeros((self._active_count, 7), dtype="f4")

        age_ratio = active[:, _AGE] / np.maximum(active[:, _LIFE], 0.01)
        age_ratio = np.clip(age_ratio, 0.0, 1.0)

        # --- Size over life ---
        base_size = active[:, _BSIZE]
        size_mode = self.get_param("size_over_life", "constant")
        if size_mode == "grow":
            computed_size = base_size * (0.3 + 0.7 * age_ratio)
        elif size_mode == "shrink":
            computed_size = base_size * (1.0 - 0.7 * age_ratio)
        elif size_mode == "pulse":
            computed_size = base_size * (0.6 + 0.4 * np.sin(age_ratio * np.pi * 4.0))
        else:  # constant
            computed_size = base_size

        # --- Fade curve ---
        fade = self.get_param("fade_curve", "linear")
        if fade == "ease_out":
            alpha = (1.0 - age_ratio) ** 0.5
        elif fade == "flash":
            alpha = np.where(age_ratio < 0.7, 1.0, 1.0 - (age_ratio - 0.7) / 0.3)
        else:  # linear
            alpha = 1.0 - age_ratio
        alpha = np.clip(alpha, 0.0, 1.0).astype("f4")

        # --- Color over life ---
        colors = self.params.params.get("_colors", [(0.0, 1.0, 0.67)])
        colors_arr = np.array(colors, dtype="f4")
        n_colors = len(colors_arr)

        if self.get_param("color_over_life", False) and n_colors > 1:
            # Interpolate through palette based on age
            palette_pos = age_ratio * (n_colors - 1)
            idx_lo = np.clip(np.floor(palette_pos).astype(int), 0, n_colors - 2)
            idx_hi = idx_lo + 1
            frac = (palette_pos - idx_lo).astype("f4")
            r = colors_arr[idx_lo, 0] * (1 - frac) + colors_arr[idx_hi, 0] * frac
            g = colors_arr[idx_lo, 1] * (1 - frac) + colors_arr[idx_hi, 1] * frac
            b = colors_arr[idx_lo, 2] * (1 - frac) + colors_arr[idx_hi, 2] * frac
            vbo_data[:, 3] = r
            vbo_data[:, 4] = g
            vbo_data[:, 5] = b
        else:
            vbo_data[:, 3] = active[:, _R]
            vbo_data[:, 4] = active[:, _G]
            vbo_data[:, 5] = active[:, _B]

        vbo_data[:, 0] = active[:, _X]
        vbo_data[:, 1] = active[:, _Y]
        vbo_data[:, 2] = computed_size
        vbo_data[:, 6] = alpha

        self._vbo.write(vbo_data.tobytes())

        if "u_resolution" in self._program:
            self._program["u_resolution"].value = resolution  # type: ignore[reportAttributeAccessIssue]
        self._vao.render(moderngl.POINTS, vertices=self._active_count)

        self.ctx.disable(moderngl.PROGRAM_POINT_SIZE | moderngl.BLEND)

    def _update_particles(self, dt: float, frame: FrameAnalysis) -> None:
        """Update particle positions, velocities, and ages."""
        if self._active_count == 0:
            return

        active = self._particles[: self._active_count]

        # --- Gravity ---
        gravity_x = self.get_param("gravity_x", 0.0)
        gravity_y = self.get_param("gravity_y", -0.1)
        active[:, _VX] += gravity_x * dt
        active[:, _VY] += gravity_y * dt

        # --- Turbulence ---
        turbulence = self.get_param("turbulence", 0.0)
        if turbulence > 0.0:
            nx, ny = _simple_noise(active[:, _X], active[:, _Y], self._time)
            strength = turbulence * 0.5 * dt
            # Modulate turbulence by audio amplitude for reactivity
            strength *= (1.0 + frame.amplitude * 2.0)
            active[:, _VX] += nx * strength
            active[:, _VY] += ny * strength

        # --- Radial force (attraction/repulsion from spawn point) ---
        radial_force = self.get_param("radial_force", 0.0)
        if radial_force != 0.0:
            spawn_x = self.get_param("spawn_x", 0.5)
            spawn_y = self.get_param("spawn_y", 0.5)
            dx = active[:, _X] - spawn_x
            dy = active[:, _Y] - spawn_y
            dist = np.sqrt(dx * dx + dy * dy)
            dist = np.maximum(dist, 0.01)  # avoid division by zero
            # Positive = repel, negative = attract
            force_mag = radial_force * 0.3 * dt
            active[:, _VX] += (dx / dist) * force_mag
            active[:, _VY] += (dy / dist) * force_mag

        # --- Vortex (rotational force) ---
        vortex = self.get_param("vortex", 0.0)
        if vortex != 0.0:
            spawn_x = self.get_param("spawn_x", 0.5)
            spawn_y = self.get_param("spawn_y", 0.5)
            dx = active[:, _X] - spawn_x
            dy = active[:, _Y] - spawn_y
            # Perpendicular direction for rotation
            vortex_strength = vortex * 0.5 * dt
            active[:, _VX] += -dy * vortex_strength
            active[:, _VY] += dx * vortex_strength

        # --- Drag ---
        drag = self.get_param("drag", 0.0)
        if drag > 0.0:
            drag_factor = (1.0 - drag) ** (dt * 60.0)  # framerate-independent drag
            active[:, _VX] *= drag_factor
            active[:, _VY] *= drag_factor

        # --- Update position ---
        active[:, _X] += active[:, _VX] * dt
        active[:, _Y] += active[:, _VY] * dt

        # --- Update age ---
        active[:, _AGE] += dt

        # --- Remove dead particles ---
        alive_mask = (
            (active[:, _AGE] < active[:, _LIFE])
            & (active[:, _X] > -0.5) & (active[:, _X] < 1.5)
            & (active[:, _Y] > -0.5) & (active[:, _Y] < 1.5)
        )

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

        # --- Spawn count based on amplitude + beat ---
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
        n_colors = len(colors_arr)

        start = self._active_count
        end = start + spawn_count
        n = spawn_count

        # --- Speed reactivity: mid-freq boosts initial speed ---
        speed_reactivity = self.get_param("speed_reactivity", 0.3)
        mid_energy = frame.frequency_bands_norm.get("mid", 0.0)
        speed_mult = 1.0 + speed_reactivity * mid_energy * 2.0

        # --- Beat velocity boost (not just count) ---
        if frame.beat:
            speed_mult *= (1.0 + 0.5 * frame.beat_intensity)

        angles = np.random.uniform(0, 2 * np.pi, n).astype("f4")
        speeds = (
            np.random.uniform(speed_min, speed_max, n).astype("f4")
            * spread * (1.0 + frame.amplitude) * speed_mult
        )

        # --- Size reactivity: bass inflates particle size ---
        size_reactivity = self.get_param("size_reactivity", 0.3)
        bass_energy = frame.frequency_bands_norm.get("bass", 0.0)
        size_mult = 1.0 + size_reactivity * bass_energy * 3.0

        # --- Color shift reactivity: frequency drives palette selection ---
        color_shift = self.get_param("color_shift_reactivity", 0.0)
        if color_shift > 0.0 and n_colors > 1:
            # Spectral centroid normalized to [0, 1] range to shift palette
            centroid_norm = min(frame.spectral_centroid / 8000.0, 1.0)
            shift_amount = centroid_norm * color_shift * (n_colors - 1)
            base_indices = np.random.randint(0, n_colors, n).astype("f4")
            color_indices = np.clip(
                (base_indices + shift_amount).astype(int), 0, n_colors - 1
            )
        else:
            color_indices = np.random.randint(0, n_colors, n)

        # --- Spawn positions based on mode ---
        spawn_mode = self.get_param("spawn_mode", "point")
        pos_x, pos_y = self._compute_spawn_positions(
            n, spawn_mode, spawn_x, spawn_y
        )

        # --- Velocity direction based on spawn mode ---
        vx, vy = self._compute_spawn_velocities(
            n, spawn_mode, pos_x, pos_y, spawn_x, spawn_y, angles, speeds
        )

        batch = self._particles[start:end]
        batch[:, _X] = pos_x
        batch[:, _Y] = pos_y
        batch[:, _VX] = vx
        batch[:, _VY] = vy
        batch[:, _AGE] = 0.0
        batch[:, _LIFE] = lifetime * np.random.uniform(0.5, 1.5, n).astype("f4")
        batch[:, _BSIZE] = (
            particle_size * np.random.uniform(0.5, 1.5, n).astype("f4") * size_mult
        )
        batch[:, _R:_B + 1] = colors_arr[color_indices]
        batch[:, _ALPHA] = 1.0
        batch[:, _CIDX] = color_indices.astype("f4")

        self._active_count = end

    def _compute_spawn_positions(
        self,
        n: int,
        mode: str,
        spawn_x: float,
        spawn_y: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute spawn positions for n particles based on spawn mode."""
        if mode == "line":
            # Horizontal line centered at spawn_y
            pos_x = np.random.uniform(0.0, 1.0, n).astype("f4")
            pos_y = np.full(n, spawn_y, dtype="f4")
        elif mode == "circle":
            radius = self.get_param("spawn_radius", 0.3)
            ring_angles = np.random.uniform(0, 2 * np.pi, n).astype("f4")
            # Slight variation in radius for organic look
            r = radius * np.random.uniform(0.9, 1.1, n).astype("f4")
            pos_x = (spawn_x + np.cos(ring_angles) * r).astype("f4")
            pos_y = (spawn_y + np.sin(ring_angles) * r).astype("f4")
        elif mode == "edges":
            # Spawn from random screen edges
            edge = np.random.randint(0, 4, n)
            pos_x = np.empty(n, dtype="f4")
            pos_y = np.empty(n, dtype="f4")
            rand_t = np.random.uniform(0.0, 1.0, n).astype("f4")
            # 0=bottom, 1=top, 2=left, 3=right
            bottom = edge == 0
            top = edge == 1
            left = edge == 2
            right = edge == 3
            pos_x[bottom] = rand_t[bottom]
            pos_y[bottom] = 0.0
            pos_x[top] = rand_t[top]
            pos_y[top] = 1.0
            pos_x[left] = 0.0
            pos_y[left] = rand_t[left]
            pos_x[right] = 1.0
            pos_y[right] = rand_t[right]
        elif mode == "random":
            pos_x = np.random.uniform(0.0, 1.0, n).astype("f4")
            pos_y = np.random.uniform(0.0, 1.0, n).astype("f4")
        else:  # point
            pos_x = np.full(n, spawn_x, dtype="f4")
            pos_y = np.full(n, spawn_y, dtype="f4")

        return pos_x, pos_y

    def _compute_spawn_velocities(
        self,
        n: int,
        mode: str,
        pos_x: np.ndarray,
        pos_y: np.ndarray,
        spawn_x: float,
        spawn_y: float,
        angles: np.ndarray,
        speeds: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute initial velocities based on spawn mode."""
        if mode == "edges":
            # Particles move inward from edges toward center
            dx = spawn_x - pos_x
            dy = spawn_y - pos_y
            dist = np.sqrt(dx * dx + dy * dy)
            dist = np.maximum(dist, 0.01)
            # Add some angular spread
            spread_angle = np.random.uniform(-0.4, 0.4, n).astype("f4")
            cos_s, sin_s = np.cos(spread_angle), np.sin(spread_angle)
            dir_x = dx / dist
            dir_y = dy / dist
            # Rotate direction by spread angle
            vx = (dir_x * cos_s - dir_y * sin_s) * speeds
            vy = (dir_x * sin_s + dir_y * cos_s) * speeds
        elif mode == "circle":
            # Particles move outward from circle center
            dx = pos_x - spawn_x
            dy = pos_y - spawn_y
            dist = np.sqrt(dx * dx + dy * dy)
            dist = np.maximum(dist, 0.01)
            vx = (dx / dist) * speeds
            vy = (dy / dist) * speeds
        else:
            # point / line / random — use random angles
            vx = np.cos(angles) * speeds
            vy = np.sin(angles) * speeds

        return vx.astype("f4"), vy.astype("f4")

    def cleanup(self) -> None:
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._program:
            self._program.release()

"""GIF export pipeline — two-pass palette generation via ffmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import moderngl

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoader
from wavern.core.renderer import Renderer
from wavern.core.timeline import Timeline

from wavern.core.export_config import ExportConfig

from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


def export_gif(
    audio_path: Path,
    preset: Preset,
    config: ExportConfig,
    progress_callback: Callable[[float], None] | None,
    is_cancelled: Callable[[], bool],
) -> Path:
    """Export visualization as an animated GIF via two-pass palette generation.

    Renders all frames to a temporary raw video, generates an optimised colour
    palette, then encodes the final GIF with optional dithering.

    Args:
        audio_path: Path to the source audio file.
        preset: Visualization preset to render.
        config: Export settings (resolution, fps, GIF options, etc.).
        progress_callback: Called with a 0.0–1.0 progress fraction.
        is_cancelled: Returns True when the export should be aborted.

    Returns:
        Path to the output GIF file.

    Raises:
        RuntimeError: On ffmpeg failure or cancellation.
    """
    from wavern.core.export import _find_ffmpeg  # avoid circular at module level

    ffmpeg_bin = _find_ffmpeg()

    audio_data, metadata = AudioLoader.load(str(audio_path))

    analyzer = AudioAnalyzer(
        fft_size=preset.fft_size,
        smoothing_factor=preset.smoothing,
    )
    analyzer.configure(audio_data, metadata.sample_rate)

    timeline = Timeline(metadata.duration, config.fps)

    ctx = moderngl.create_standalone_context()
    renderer = Renderer(ctx)
    renderer.set_preset(preset)
    renderer.set_duration(metadata.duration)

    if renderer._video_source is not None:
        renderer._video_source.reset()
    if renderer._overlay_video_source is not None:
        renderer._overlay_video_source.reset()

    # Scale resolution for GIF
    w, h = config.resolution
    gif_w = max(2, int(w * config.gif_scale) // 2 * 2)  # ensure even
    gif_h = max(2, int(h * config.gif_scale) // 2 * 2)

    fbo = renderer.ensure_offscreen_fbo(config.resolution)

    temp_dir = tempfile.mkdtemp(prefix="wavern_gif_")
    temp_raw = Path(temp_dir) / "raw.avi"
    palette_path = Path(temp_dir) / "palette.png"

    try:
        # Step 1: Render frames to temp raw video
        raw_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{w}x{h}", "-pix_fmt", "rgb24",
            "-r", str(config.fps),
            "-i", "pipe:0",
            "-vf", f"scale={gif_w}:{gif_h}:flags=lanczos",
            "-c:v", "rawvideo", "-pix_fmt", "rgb24",
            str(temp_raw),
        ]

        proc = subprocess.Popen(
            raw_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        logger.info(
            "GIF export: %d frames at %dx%d → %dx%d",
            timeline.total_frames, w, h, gif_w, gif_h,
        )

        # Render loop
        for frame_idx in range(timeline.total_frames):
            if is_cancelled():
                proc.kill()
                raise RuntimeError("Export cancelled")
            timestamp = timeline.frame_to_time(frame_idx)
            frame_analysis = analyzer.analyze_frame(timestamp)
            renderer.render_frame(frame_analysis, fbo, config.resolution)
            pixels = renderer.read_pixels(fbo, config.resolution, components=3)
            proc.stdin.write(pixels.tobytes())
            if progress_callback and frame_idx % 10 == 0:
                progress_callback((frame_idx + 1) / timeline.total_frames * 0.5)

        proc.stdin.close()

        # Wait for ffmpeg
        while proc.poll() is None:
            if is_cancelled():
                proc.kill()
                proc.wait()
                raise RuntimeError("Export cancelled")
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

        if proc.returncode != 0:
            stderr = proc.stderr.read().decode()
            raise RuntimeError(f"ffmpeg raw render failed: {stderr}")

        # Step 2: Generate palette
        palette_cmd = [
            ffmpeg_bin, "-y",
            "-i", str(temp_raw),
            "-vf", f"palettegen=max_colors={config.gif_max_colors}",
            str(palette_path),
        ]
        result = subprocess.run(palette_cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"GIF palette generation failed: {result.stderr.decode()}")

        # Step 3: Apply palette and produce GIF
        dither = "bayer" if config.gif_dither else "none"
        gif_cmd = [
            ffmpeg_bin, "-y",
            "-i", str(temp_raw),
            "-i", str(palette_path),
            "-lavfi", f"paletteuse=dither={dither}",
            "-loop", str(config.gif_loop),
            str(config.output_path),
        ]
        result = subprocess.run(gif_cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"GIF encoding failed: {result.stderr.decode()}")

        if progress_callback:
            progress_callback(1.0)

        logger.info("GIF export complete: %s", config.output_path)
        return config.output_path

    finally:
        renderer.cleanup()
        ctx.release()
        shutil.rmtree(temp_dir, ignore_errors=True)

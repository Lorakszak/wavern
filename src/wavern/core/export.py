"""Video export pipeline — renders visualization to video file via ffmpeg."""

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

import moderngl
import numpy as np

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoader
from wavern.core.codecs import get_codec_family, supports_alpha
from wavern.core.export_config import ExportConfig
from wavern.core.ffmpeg_cmd import build_ffmpeg_cmd
from wavern.core.renderer import Renderer
from wavern.core.timeline import Timeline
from wavern.presets.schema import Preset

__all__ = ["ExportConfig", "ExportPipeline", "compute_fade_factor"]

logger = logging.getLogger(__name__)


def compute_fade_factor(
    timestamp: float, duration: float, fade_in: float, fade_out: float
) -> float:
    """Compute opacity multiplier (0.0-1.0) for fade-in/out at a given timestamp.

    Args:
        timestamp: Current position in seconds.
        duration: Total duration in seconds.
        fade_in: Fade-in duration in seconds (0 = no fade-in).
        fade_out: Fade-out duration in seconds (0 = no fade-out).

    Returns:
        A factor between 0.0 and 1.0 to multiply pixel values by.
    """
    factor = 1.0
    if fade_in > 0.0 and timestamp < fade_in:
        factor = min(factor, timestamp / fade_in)
    if fade_out > 0.0 and timestamp > duration - fade_out:
        factor = min(factor, (duration - timestamp) / fade_out)
    return max(0.0, min(1.0, factor))


def _start_stderr_drain(proc: subprocess.Popen[bytes]) -> Callable[[], str]:
    """Start a daemon thread to drain process stderr, preventing pipe deadlock.

    Returns a callable that joins the thread and returns the collected output.
    """
    assert proc.stderr is not None
    stderr = proc.stderr
    chunks: list[bytes] = []
    thread = threading.Thread(
        target=lambda: chunks.append(stderr.read()),
        daemon=True,
    )
    thread.start()

    def get_stderr() -> str:
        thread.join(timeout=10)
        return b"".join(chunks).decode(errors="replace")

    return get_stderr


def _find_ffmpeg() -> str:
    """Find ffmpeg binary — prefer system install, fallback to imageio-ffmpeg."""
    path = shutil.which("ffmpeg")
    if path:
        return path

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg system-wide or `pip install imageio-ffmpeg`."
        )


class ExportPipeline:
    """Renders the full audio file frame-by-frame and encodes to video via ffmpeg.

    Uses a headless moderngl context, so it works without a display server.
    """

    def __init__(
        self,
        audio_path: Path,
        preset: Preset,
        export_config: ExportConfig,
        progress_callback: Callable[[float], None] | None = None,
    ) -> None:
        self._audio_path = audio_path
        self._preset = preset
        self._config = export_config
        self._progress_callback = progress_callback
        self._cancelled = threading.Event()

    def run(self) -> Path:
        """Execute the full export pipeline. Returns path to the output video."""
        if self._config.container == "gif":
            from wavern.core.gif_export import export_gif
            return export_gif(
                self._audio_path,
                self._preset,
                self._config,
                self._progress_callback,
                self._cancelled.is_set,
            )
        return self._export_video()

    def _export_video(self) -> Path:
        """Standard video export (mp4/webm/mov)."""
        ffmpeg_bin = _find_ffmpeg()

        audio_data, metadata = AudioLoader.load(str(self._audio_path))

        analyzer = AudioAnalyzer(
            fft_size=self._preset.fft_size,
            smoothing_factor=self._preset.smoothing,
        )
        analyzer.configure(audio_data, metadata.sample_rate)

        timeline = Timeline(metadata.duration, self._config.fps)

        has_alpha = (
            self._preset.background.type == "none"
            and supports_alpha(self._config.container, self._config.video_codec)
        )

        ctx = moderngl.create_standalone_context()
        renderer = Renderer(ctx)
        renderer.set_preset(self._preset)
        renderer.set_duration(metadata.duration)

        if renderer._video_source is not None:
            renderer._video_source.reset()
        if renderer._overlay_video_source is not None:
            renderer._overlay_video_source.reset()

        fbo = renderer.ensure_offscreen_fbo(self._config.resolution)

        temp_dir = tempfile.mkdtemp(prefix="wavern_export_")
        temp_video = Path(temp_dir) / f"video_only.{self._config.container}"

        try:
            w, h = self._config.resolution
            if has_alpha:
                input_pix_fmt = "rgba"
                components = 4
                family = get_codec_family(self._config.video_codec)
                if family == "prores":
                    output_pix_fmt = "yuva444p10le"
                else:
                    output_pix_fmt = "yuva420p"
            else:
                input_pix_fmt = "rgb24"
                components = 3
                family = get_codec_family(self._config.video_codec)
                if family == "prores":
                    output_pix_fmt = "yuv422p10le"
                else:
                    output_pix_fmt = self._config.pixel_format

            ffmpeg_cmd, using_hw = build_ffmpeg_cmd(
                self._config, ffmpeg_bin, w, h,
                input_pix_fmt, output_pix_fmt, temp_video,
            )
            logger.debug("ffmpeg command: %s", ffmpeg_cmd)

            proc: subprocess.Popen[bytes] = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            logger.info(
                "Exporting %d frames at %dx%d, %dfps (alpha=%s, codec=%s)",
                timeline.total_frames, w, h, self._config.fps,
                has_alpha, self._config.video_codec,
            )

            get_stderr = _start_stderr_drain(proc)

            hw_failed = False
            try:
                self._render_frames(renderer, analyzer, timeline, fbo, proc, components)
            except (BrokenPipeError, OSError):
                if using_hw:
                    hw_failed = True
                    logger.warning(
                        "HW encoder failed (broken pipe), falling back to software encoding"
                    )
                    proc.kill()
                    proc.wait()
                else:
                    raise

            if not hw_failed:
                assert proc.stdin is not None
                proc.stdin.close()
                self._wait_for_process(proc)

                if proc.returncode != 0:
                    if using_hw:
                        hw_failed = True
                        logger.warning(
                            "HW encoder returned error, falling back to software encoding"
                        )
                    else:
                        stderr_output = get_stderr()
                        logger.error("ffmpeg failed with stderr: %s", stderr_output)
                        raise RuntimeError(f"ffmpeg failed: {stderr_output}")

            # Fallback: re-render with software encoding
            if hw_failed:
                renderer.cleanup()
                ctx.release()

                ctx = moderngl.create_standalone_context()
                renderer = Renderer(ctx)
                renderer.set_preset(self._preset)
                renderer.set_duration(metadata.duration)
                if renderer._video_source is not None:
                    renderer._video_source.reset()
                if renderer._overlay_video_source is not None:
                    renderer._overlay_video_source.reset()
                fbo = renderer.ensure_offscreen_fbo(self._config.resolution)

                analyzer = AudioAnalyzer(
                    fft_size=self._preset.fft_size,
                    smoothing_factor=self._preset.smoothing,
                )
                analyzer.configure(audio_data, metadata.sample_rate)

                ffmpeg_cmd, _ = build_ffmpeg_cmd(
                    self._config, ffmpeg_bin, w, h,
                    input_pix_fmt, output_pix_fmt, temp_video,
                    force_software=True,
                )

                logger.info("Retrying with software encoder: %s", self._config.video_codec)

                proc = subprocess.Popen(  # type: ignore[assignment]
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

                get_stderr = _start_stderr_drain(proc)

                self._render_frames(renderer, analyzer, timeline, fbo, proc, components)
                assert proc.stdin is not None
                proc.stdin.close()
                self._wait_for_process(proc)

                if proc.returncode != 0:
                    stderr_output = get_stderr()
                    logger.error("ffmpeg software fallback failed: %s", stderr_output)
                    raise RuntimeError(f"ffmpeg failed: {stderr_output}")

            self._mux_audio(ffmpeg_bin, temp_video, self._audio_path,
                            self._config.output_path)

            if self._config.intro_path or self._config.outro_path:
                from wavern.core.video_concat import (
                    ConcatTarget,
                    resolve_audio_codec,
                    run_concat_pipeline,
                )

                actual_audio_codec = resolve_audio_codec(
                    self._config.container, self._config.audio_codec,
                )
                target = ConcatTarget(
                    resolution=self._config.resolution,
                    fps=self._config.fps,
                    video_codec=self._config.video_codec,
                    audio_codec=actual_audio_codec,
                    audio_bitrate=self._config.audio_bitrate,
                    pixel_format=self._config.pixel_format,
                    container=self._config.container,
                    crf=self._config.crf,
                )

                def concat_progress(p: float) -> None:
                    if self._progress_callback:
                        self._progress_callback(0.85 + p * 0.15)

                run_concat_pipeline(
                    ffmpeg_bin=ffmpeg_bin,
                    rendered_video=self._config.output_path,
                    output_path=self._config.output_path,
                    intro_path=self._config.intro_path,
                    outro_path=self._config.outro_path,
                    intro_keep_audio=self._config.intro_keep_audio,
                    outro_keep_audio=self._config.outro_keep_audio,
                    target=target,
                    cancelled=self._cancelled,
                    progress_callback=concat_progress,
                    intro_fade_in=self._config.intro_fade_in,
                    intro_fade_out=self._config.intro_fade_out,
                    outro_fade_in=self._config.outro_fade_in,
                    outro_fade_out=self._config.outro_fade_out,
                )

            if self._progress_callback:
                self._progress_callback(1.0)

            logger.info("Export complete: %s", self._config.output_path)
            return self._config.output_path

        finally:
            renderer.cleanup()
            ctx.release()
            import shutil as _shutil
            _shutil.rmtree(temp_dir, ignore_errors=True)

    def _render_frames(
        self,
        renderer: Renderer,
        analyzer: AudioAnalyzer,
        timeline: Timeline,
        fbo: moderngl.Framebuffer,
        proc: subprocess.Popen[bytes],
        components: int,
    ) -> None:
        """Render all frames and pipe to ffmpeg process."""
        assert proc.stdin is not None
        fade_in = self._preset.fade_in
        fade_out = self._preset.fade_out
        has_fade = fade_in > 0.0 or fade_out > 0.0

        for frame_idx in range(timeline.total_frames):
            if self._cancelled.is_set():
                proc.kill()
                try:
                    proc.stdin.close()
                except OSError:
                    pass
                proc.wait()
                raise RuntimeError("Export cancelled")

            timestamp = timeline.frame_to_time(frame_idx)
            frame_analysis = analyzer.analyze_frame(timestamp)
            renderer.render_frame(frame_analysis, fbo, self._config.resolution)
            pixels = renderer.read_pixels(
                fbo, self._config.resolution, components=components
            )

            if has_fade:
                fade = compute_fade_factor(
                    timestamp, timeline.duration, fade_in, fade_out
                )
                if fade < 1.0:
                    pixels = (pixels.astype(np.float32) * fade).astype(np.uint8)

            proc.stdin.write(pixels.tobytes())

            if frame_idx % 100 == 0:
                logger.debug("Rendered frame %d/%d", frame_idx, timeline.total_frames)
            if self._progress_callback and frame_idx % 10 == 0:
                has_concat = bool(self._config.intro_path or self._config.outro_path)
                scale = 0.85 if has_concat else 1.0
                progress = ((frame_idx + 1) / timeline.total_frames) * scale
                self._progress_callback(progress)

    def _wait_for_process(self, proc: subprocess.Popen[bytes]) -> None:
        """Wait for ffmpeg process, checking for cancellation."""
        while proc.poll() is None:
            if self._cancelled.is_set():
                proc.kill()
                proc.wait()
                raise RuntimeError("Export cancelled")
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

    def _mux_audio(
        self,
        ffmpeg_bin: str,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> None:
        """Combine rendered video with original audio using ffmpeg."""
        from wavern.core.video_concat import resolve_audio_codec

        audio_codec = resolve_audio_codec(self._config.container, self._config.audio_codec)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", audio_codec,
            "-b:a", self._config.audio_bitrate,
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Audio muxing failed: {result.stderr.decode()}")

    def cancel(self) -> None:
        """Signal the export loop to stop."""
        self._cancelled.set()

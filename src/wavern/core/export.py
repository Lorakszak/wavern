"""Video export pipeline — renders visualization to video file via ffmpeg."""

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

import moderngl

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoader
from wavern.core.codecs import get_codec_family, supports_alpha
from wavern.core.export_config import ExportConfig
from wavern.core.ffmpeg_cmd import build_ffmpeg_cmd
from wavern.core.renderer import Renderer
from wavern.core.timeline import Timeline
from wavern.presets.schema import Preset

__all__ = ["ExportConfig", "ExportPipeline"]

logger = logging.getLogger(__name__)


def _start_stderr_drain(proc: subprocess.Popen) -> Callable[[], str]:
    """Start a daemon thread to drain process stderr, preventing pipe deadlock.

    Returns a callable that joins the thread and returns the collected output.
    """
    chunks: list[bytes] = []
    thread = threading.Thread(
        target=lambda: chunks.append(proc.stderr.read()),
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
        self._cancelled = False

    def run(self) -> Path:
        """Execute the full export pipeline. Returns path to the output video."""
        if self._config.container == "gif":
            from wavern.core.gif_export import export_gif
            return export_gif(
                self._audio_path,
                self._preset,
                self._config,
                self._progress_callback,
                lambda: self._cancelled,
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

            proc = subprocess.Popen(
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
                proc.stdin.close()
                self._wait_for_process(proc)

                if proc.returncode != 0:
                    if using_hw:
                        hw_failed = True
                        logger.warning(
                            "HW encoder returned error, falling back to software encoding"
                        )
                    else:
                        raise RuntimeError(f"ffmpeg failed: {get_stderr()}")

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

                proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

                get_stderr = _start_stderr_drain(proc)

                self._render_frames(renderer, analyzer, timeline, fbo, proc, components)
                proc.stdin.close()
                self._wait_for_process(proc)

                if proc.returncode != 0:
                    raise RuntimeError(f"ffmpeg failed: {get_stderr()}")

            self._mux_audio(ffmpeg_bin, temp_video, self._audio_path,
                            self._config.output_path)

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
        fbo: object,
        proc: subprocess.Popen,
        components: int,
    ) -> None:
        """Render all frames and pipe to ffmpeg process."""
        for frame_idx in range(timeline.total_frames):
            if self._cancelled:
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
            proc.stdin.write(pixels.tobytes())

            if self._progress_callback and frame_idx % 10 == 0:
                progress = (frame_idx + 1) / timeline.total_frames
                self._progress_callback(progress)

    def _wait_for_process(self, proc: subprocess.Popen) -> None:
        """Wait for ffmpeg process, checking for cancellation."""
        while proc.poll() is None:
            if self._cancelled:
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
        audio_codec = self._config.audio_codec
        container = self._config.container

        if container == "webm":
            audio_codec = "libopus"
        elif container == "mov":
            audio_codec = "aac"

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
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio muxing failed: {result.stderr.decode()}")

    def cancel(self) -> None:
        """Signal the export loop to stop."""
        self._cancelled = True

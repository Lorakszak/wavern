"""Video export pipeline — renders visualization to video file via ffmpeg."""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import moderngl

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoader
from wavern.core.renderer import Renderer
from wavern.core.timeline import Timeline
from wavern.presets.schema import Preset

logger = logging.getLogger(__name__)


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


@dataclass
class ExportConfig:
    """Video export settings."""

    output_path: Path
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 60
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    video_bitrate: str = "8M"
    pixel_format: str = "yuv420p"
    container: str = "mp4"
    crf: int = 18


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
        """Execute the full export pipeline. Returns path to the output video.

        Steps:
            1. Create standalone moderngl context
            2. Load audio
            3. Configure AudioAnalyzer
            4. Create Renderer, set preset
            5. Open ffmpeg subprocess
            6. Render each frame → pipe to ffmpeg
            7. Mux audio track
        """
        ffmpeg_bin = _find_ffmpeg()

        # Load audio
        audio_data, metadata = AudioLoader.load(str(self._audio_path))

        # Setup analyzer
        analyzer = AudioAnalyzer(
            fft_size=self._preset.fft_size,
            smoothing_factor=self._preset.smoothing,
        )
        analyzer.configure(audio_data, metadata.sample_rate)

        # Timeline
        timeline = Timeline(metadata.duration, self._config.fps)

        # Determine if we need alpha (transparent background)
        has_alpha = self._preset.background.type == "none"

        # Create headless OpenGL context
        ctx = moderngl.create_standalone_context()

        # Setup renderer
        renderer = Renderer(ctx)
        renderer.set_preset(self._preset)
        renderer.set_duration(metadata.duration)

        # Reset video sources so export starts from frame 0
        if renderer._video_source is not None:
            renderer._video_source.reset()
        if renderer._overlay_video_source is not None:
            renderer._overlay_video_source.reset()

        fbo = renderer.ensure_offscreen_fbo(self._config.resolution)

        # Render to temporary video file (no audio)
        temp_dir = tempfile.mkdtemp(prefix="wavern_export_")
        temp_video = Path(temp_dir) / f"video_only.{self._config.container}"

        try:
            # Start ffmpeg process
            w, h = self._config.resolution
            if has_alpha:
                input_pix_fmt = "rgba"
                output_pix_fmt = "yuva420p"
                components = 4
            else:
                input_pix_fmt = "rgb24"
                output_pix_fmt = self._config.pixel_format
                components = 3

            ffmpeg_cmd = [
                ffmpeg_bin,
                "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{w}x{h}",
                "-pix_fmt", input_pix_fmt,
                "-r", str(self._config.fps),
                "-i", "pipe:0",
                "-c:v", self._config.video_codec,
                "-pix_fmt", output_pix_fmt,
            ]

            # VP9 needs -b:v 0 for CRF mode + speed flags for reasonable encode time
            if self._config.video_codec == "libvpx-vp9":
                ffmpeg_cmd += [
                    "-b:v", "0",
                    "-crf", str(self._config.crf),
                    "-row-mt", "1",
                    "-speed", "4",
                ]
            else:
                ffmpeg_cmd += ["-crf", str(self._config.crf)]

            ffmpeg_cmd.append(str(temp_video))

            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            logger.info(
                "Exporting %d frames at %dx%d, %dfps (alpha=%s)",
                timeline.total_frames,
                w, h,
                self._config.fps,
                has_alpha,
            )

            for frame_idx in range(timeline.total_frames):
                if self._cancelled:
                    proc.kill()
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

            proc.stdin.close()

            # Wait for ffmpeg to finish, checking for cancellation periodically
            while proc.poll() is None:
                if self._cancelled:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError("Export cancelled")
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode()
                raise RuntimeError(f"ffmpeg failed: {stderr}")

            # Mux audio
            self._mux_audio(ffmpeg_bin, temp_video, self._audio_path, self._config.output_path)

            if self._progress_callback:
                self._progress_callback(1.0)

            logger.info("Export complete: %s", self._config.output_path)
            return self._config.output_path

        finally:
            renderer.cleanup()
            ctx.release()
            # Cleanup temp files
            import shutil as _shutil
            _shutil.rmtree(temp_dir, ignore_errors=True)

    def _mux_audio(
        self,
        ffmpeg_bin: str,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> None:
        """Combine rendered video with original audio using ffmpeg."""
        # WebM requires libopus/libvorbis audio codec
        audio_codec = self._config.audio_codec
        if self._config.container == "webm":
            audio_codec = "libopus"

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", audio_codec,
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio muxing failed: {result.stderr.decode()}")

    def cancel(self) -> None:
        """Signal the export loop to stop."""
        self._cancelled = True

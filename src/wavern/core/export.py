"""Video export pipeline — renders visualization to video file via ffmpeg."""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import moderngl

from wavern.core.audio_analyzer import AudioAnalyzer
from wavern.core.audio_loader import AudioLoader
from wavern.core.codecs import get_codec_family, supports_alpha, supports_audio
from wavern.core.hwaccel import (
    HWAccelBackend,
    build_hw_input_flags,
    get_hw_encoder,
    map_quality_to_hw,
)
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
    encoder_speed: str = "medium"
    audio_bitrate: str = "192k"
    quality_preset: str = "high"
    prores_profile: int = 3
    gif_max_colors: int = 256
    gif_dither: bool = True
    gif_loop: int = 0
    gif_scale: float = 1.0
    hw_accel: str = "auto"  # "auto" | "off"


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

    def _build_ffmpeg_cmd(
        self,
        ffmpeg_bin: str,
        w: int,
        h: int,
        input_pix_fmt: str,
        output_pix_fmt: str,
        output_path: Path,
        force_software: bool = False,
    ) -> tuple[list[str], bool]:
        """Build the ffmpeg encoding command based on codec settings.

        Attempts hardware-accelerated encoding when hw_accel is "auto" and a
        compatible GPU encoder is detected. Falls back to software encoding
        otherwise.

        Args:
            ffmpeg_bin: Path to ffmpeg binary.
            w: Video width.
            h: Video height.
            input_pix_fmt: Raw input pixel format (e.g. "rgb24", "rgba").
            output_pix_fmt: Output pixel format for the encoder.
            output_path: Path for the output file.
            force_software: If True, skip HW encoder detection entirely.

        Returns:
            Tuple of (ffmpeg command args, whether HW encoding is used).
        """
        codec = self._config.video_codec
        family = get_codec_family(codec)

        # Check for hardware encoder
        needs_alpha = input_pix_fmt == "rgba"
        hw_enc = None
        if not force_software:
            hw_enc = get_hw_encoder(codec, self._config.hw_accel, needs_alpha=needs_alpha)

        cmd = [ffmpeg_bin, "-y"]

        # HW backend init flags (e.g. VAAPI device)
        if hw_enc is not None:
            hw_input_flags = build_hw_input_flags(hw_enc, input_pix_fmt)
            cmd.extend(hw_input_flags)

        cmd += [
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{w}x{h}",
            "-pix_fmt", input_pix_fmt,
            "-r", str(self._config.fps),
            "-i", "pipe:0",
        ]

        using_hw = False
        if hw_enc is not None:
            # Hardware encoding path
            logger.info(
                "Using HW encoder: %s (%s)",
                hw_enc.encoder_name, hw_enc.backend.value,
            )
            using_hw = True
            cmd += ["-c:v", hw_enc.encoder_name]
            cmd += map_quality_to_hw(
                hw_enc, self._config.crf, self._config.encoder_speed,
            )
            # VAAPI manages pix_fmt via filter, others need it explicit
            if hw_enc.backend != HWAccelBackend.VAAPI:
                cmd += ["-pix_fmt", output_pix_fmt]
        elif family in ("x264", "x265"):
            cmd += [
                "-c:v", codec,
                "-preset", self._config.encoder_speed,
                "-crf", str(self._config.crf),
                "-pix_fmt", output_pix_fmt,
            ]
            if family == "x265":
                cmd += ["-tag:v", "hvc1"]
        elif family == "vp9":
            cmd += [
                "-c:v", codec,
                "-b:v", "0",
                "-crf", str(self._config.crf),
                "-row-mt", "1",
                "-speed", self._config.encoder_speed,
                "-pix_fmt", output_pix_fmt,
            ]
        elif family == "av1":
            cmd += [
                "-c:v", codec,
                "-b:v", "0",
                "-crf", str(self._config.crf),
                "-cpu-used", self._config.encoder_speed,
                "-row-mt", "1",
                "-pix_fmt", output_pix_fmt,
            ]
        elif family == "prores":
            cmd += [
                "-c:v", codec,
                "-profile:v", str(self._config.prores_profile),
                "-pix_fmt", output_pix_fmt,
            ]

        cmd.append(str(output_path))
        return cmd, using_hw

    def run(self) -> Path:
        """Execute the full export pipeline. Returns path to the output video."""
        if self._config.container == "gif":
            return self._export_gif()
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

            ffmpeg_cmd, using_hw = self._build_ffmpeg_cmd(
                ffmpeg_bin, w, h, input_pix_fmt, output_pix_fmt, temp_video,
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

            hw_failed = False
            try:
                self._render_frames(renderer, analyzer, timeline, fbo, proc, components)
            except (BrokenPipeError, OSError) as e:
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
                        stderr = proc.stderr.read().decode()
                        raise RuntimeError(f"ffmpeg failed: {stderr}")

            # Fallback: re-render with software encoding
            if hw_failed:
                renderer.cleanup()
                ctx.release()

                # Re-create rendering context and state
                ctx = moderngl.create_standalone_context()
                renderer = Renderer(ctx)
                renderer.set_preset(self._preset)
                renderer.set_duration(metadata.duration)
                if renderer._video_source is not None:
                    renderer._video_source.reset()
                if renderer._overlay_video_source is not None:
                    renderer._overlay_video_source.reset()
                fbo = renderer.ensure_offscreen_fbo(self._config.resolution)

                # Re-create analyzer to reset position
                analyzer = AudioAnalyzer(
                    fft_size=self._preset.fft_size,
                    smoothing_factor=self._preset.smoothing,
                )
                analyzer.configure(audio_data, metadata.sample_rate)

                ffmpeg_cmd, _ = self._build_ffmpeg_cmd(
                    ffmpeg_bin, w, h, input_pix_fmt, output_pix_fmt, temp_video,
                    force_software=True,
                )

                logger.info("Retrying with software encoder: %s", self._config.video_codec)

                proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

                self._render_frames(renderer, analyzer, timeline, fbo, proc, components)
                proc.stdin.close()
                self._wait_for_process(proc)

                if proc.returncode != 0:
                    stderr = proc.stderr.read().decode()
                    raise RuntimeError(f"ffmpeg failed: {stderr}")

            # Mux audio
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

    def _export_gif(self) -> Path:
        """GIF export via two-pass palette generation."""
        ffmpeg_bin = _find_ffmpeg()

        audio_data, metadata = AudioLoader.load(str(self._audio_path))

        analyzer = AudioAnalyzer(
            fft_size=self._preset.fft_size,
            smoothing_factor=self._preset.smoothing,
        )
        analyzer.configure(audio_data, metadata.sample_rate)

        timeline = Timeline(metadata.duration, self._config.fps)

        ctx = moderngl.create_standalone_context()
        renderer = Renderer(ctx)
        renderer.set_preset(self._preset)
        renderer.set_duration(metadata.duration)

        if renderer._video_source is not None:
            renderer._video_source.reset()
        if renderer._overlay_video_source is not None:
            renderer._overlay_video_source.reset()

        # Scale resolution for GIF
        w, h = self._config.resolution
        gif_w = max(2, int(w * self._config.gif_scale) // 2 * 2)  # ensure even
        gif_h = max(2, int(h * self._config.gif_scale) // 2 * 2)

        fbo = renderer.ensure_offscreen_fbo(self._config.resolution)

        temp_dir = tempfile.mkdtemp(prefix="wavern_gif_")
        temp_raw = Path(temp_dir) / "raw.avi"
        palette_path = Path(temp_dir) / "palette.png"

        try:
            # Step 1: Render frames to temp raw video
            raw_cmd = [
                ffmpeg_bin, "-y",
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{w}x{h}", "-pix_fmt", "rgb24",
                "-r", str(self._config.fps),
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

            self._render_frames(renderer, analyzer, timeline, fbo, proc, 3)

            proc.stdin.close()
            self._wait_for_process(proc)

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode()
                raise RuntimeError(f"ffmpeg raw render failed: {stderr}")

            # Step 2: Generate palette
            palette_cmd = [
                ffmpeg_bin, "-y",
                "-i", str(temp_raw),
                "-vf", f"palettegen=max_colors={self._config.gif_max_colors}",
                str(palette_path),
            ]
            result = subprocess.run(palette_cmd, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(f"GIF palette generation failed: {result.stderr.decode()}")

            # Step 3: Apply palette and produce GIF
            dither = "bayer" if self._config.gif_dither else "none"
            gif_cmd = [
                ffmpeg_bin, "-y",
                "-i", str(temp_raw),
                "-i", str(palette_path),
                "-lavfi", f"paletteuse=dither={dither}",
                "-loop", str(self._config.gif_loop),
                str(self._config.output_path),
            ]
            result = subprocess.run(gif_cmd, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(f"GIF encoding failed: {result.stderr.decode()}")

            if self._progress_callback:
                self._progress_callback(1.0)

            logger.info("GIF export complete: %s", self._config.output_path)
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

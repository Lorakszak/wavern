"""Video concatenation — intro/outro joining via ffmpeg filter_complex."""

import logging
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import av

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoClipInfo:
    """Metadata for a video clip."""

    path: Path
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    video_codec: str
    audio_codec: str | None
    audio_sample_rate: int


@dataclass(frozen=True)
class ClipMismatch:
    """Describes how a clip differs from the target render settings."""

    clip_label: str
    resolution_match: bool
    fps_match: bool
    clip_resolution: tuple[int, int]
    clip_fps: float
    target_resolution: tuple[int, int]
    target_fps: int


@dataclass(frozen=True)
class ConcatTarget:
    """Target encoding parameters for the concatenated output."""

    resolution: tuple[int, int]
    fps: int
    video_codec: str
    audio_codec: str
    audio_bitrate: str
    pixel_format: str
    container: str
    crf: int


def probe_video_clip(path: Path) -> VideoClipInfo:
    """Probe a video file and return its metadata.

    Args:
        path: Path to the video file.

    Returns:
        VideoClipInfo with stream metadata.

    Raises:
        ValueError: If the file cannot be opened or has no video stream.
    """
    try:
        container = av.open(str(path))
    except Exception as e:
        raise ValueError(f"Cannot open video: {path} — {e}") from e

    try:
        if not container.streams.video:
            raise ValueError(f"No video stream in {path}")

        vstream = container.streams.video[0]
        width = vstream.codec_context.width
        height = vstream.codec_context.height
        avg_rate = vstream.average_rate
        fps: float = float(avg_rate) if avg_rate is not None else 30.0

        if vstream.duration is not None and vstream.time_base is not None:
            time_base = float(vstream.time_base)
            duration = float(vstream.duration) * time_base
        elif container.duration is not None:
            duration = float(container.duration) / av.time_base
        else:
            duration = 0.0

        video_codec = vstream.codec_context.name or "unknown"

        has_audio = len(container.streams.audio) > 0
        audio_codec: str | None = None
        audio_sample_rate = 0
        if has_audio:
            astream = container.streams.audio[0]
            audio_codec = astream.codec_context.name
            audio_sample_rate = astream.codec_context.sample_rate or 0

        return VideoClipInfo(
            path=path,
            width=width,
            height=height,
            fps=fps,
            duration=duration,
            has_audio=has_audio,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_sample_rate=audio_sample_rate,
        )
    finally:
        container.close()


def detect_mismatches(
    clips: list[tuple[str, VideoClipInfo]],
    target_resolution: tuple[int, int],
    target_fps: int,
) -> list[ClipMismatch]:
    """Compare clips against target render settings.

    FPS tolerance: 1% of target fps (handles 29.97 vs 30, etc.).

    Returns:
        List of mismatches (empty if all clips match).
    """
    fps_tolerance = target_fps * 0.01
    mismatches: list[ClipMismatch] = []
    for label, clip in clips:
        res_match = (clip.width, clip.height) == target_resolution
        fps_match = abs(clip.fps - target_fps) <= fps_tolerance
        if not res_match or not fps_match:
            mismatches.append(ClipMismatch(
                clip_label=label,
                resolution_match=res_match,
                fps_match=fps_match,
                clip_resolution=(clip.width, clip.height),
                clip_fps=clip.fps,
                target_resolution=target_resolution,
                target_fps=target_fps,
            ))
    return mismatches


def resolve_audio_codec(container: str, config_audio_codec: str) -> str:
    """Resolve the actual audio codec based on container format.

    Args:
        container: Output container format (mp4, webm, mov, etc.).
        config_audio_codec: Audio codec from config.

    Returns:
        The resolved audio codec string.
    """
    if container == "webm":
        return "libopus"
    if container == "mov":
        return "aac"
    return config_audio_codec


def build_concat_cmd(
    ffmpeg_bin: str,
    segments: list[Path],
    keep_audio_flags: list[bool],
    has_audio_flags: list[bool],
    target: ConcatTarget,
    output_path: Path,
) -> list[str]:
    """Build an ffmpeg command to concatenate video segments.

    Uses -filter_complex with per-stream scale/pad/fps filters followed by
    concat=n=N:v=1:a=1. Segments without audio (or with keep_audio=False) get
    an anullsrc silent audio stream.

    Args:
        ffmpeg_bin: Path to ffmpeg binary.
        segments: Ordered list of input video paths.
        keep_audio_flags: Whether to keep audio for each segment.
        has_audio_flags: Whether each segment actually has an audio stream.
        target: Encoding target parameters.
        output_path: Path for the concatenated output.

    Returns:
        The ffmpeg command as a list of strings.
    """
    w, h = target.resolution
    n = len(segments)

    cmd: list[str] = [ffmpeg_bin, "-y"]

    # Add inputs
    for seg in segments:
        cmd.extend(["-i", str(seg)])

    # Build filter_complex
    filter_parts: list[str] = []
    concat_inputs: list[str] = []

    for i in range(n):
        # Video: scale + pad + fps + setsar
        vfilter = (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={target.fps},setsar=1[v{i}]"
        )
        filter_parts.append(vfilter)

        # Audio: use source audio or generate silence
        use_source_audio = keep_audio_flags[i] and has_audio_flags[i]
        if use_source_audio:
            afilter = f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
        else:
            afilter = (
                f"anullsrc=r=48000:cl=stereo:d=1[silence{i}];"
                f"[silence{i}]aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
            )
        filter_parts.append(afilter)

        concat_inputs.append(f"[v{i}][a{i}]")

    # Concat filter
    concat_str = "".join(concat_inputs) + f"concat=n={n}:v=1:a=1[vout][aout]"
    filter_parts.append(concat_str)

    filter_complex = ";".join(filter_parts)
    cmd.extend(["-filter_complex", filter_complex])

    # Map outputs
    cmd.extend(["-map", "[vout]", "-map", "[aout]"])

    # Video encoding
    cmd.extend(["-c:v", target.video_codec])
    if target.video_codec not in ("prores_ks",):
        cmd.extend(["-crf", str(target.crf)])
    cmd.extend(["-pix_fmt", target.pixel_format])

    # VP9 requires -b:v 0 for CRF mode
    if target.video_codec in ("libvpx-vp9", "libvpx"):
        cmd.extend(["-b:v", "0", "-speed", "4", "-row-mt", "1"])

    # Audio encoding
    cmd.extend(["-c:a", target.audio_codec, "-b:a", target.audio_bitrate])

    cmd.append(str(output_path))
    return cmd


def run_concat_pipeline(
    ffmpeg_bin: str,
    rendered_video: Path,
    output_path: Path,
    intro_path: Path | None,
    outro_path: Path | None,
    intro_keep_audio: bool,
    outro_keep_audio: bool,
    target: ConcatTarget,
    cancelled: threading.Event,
    progress_callback: Callable[[float], None] | None = None,
) -> Path:
    """Concatenate intro/outro with the rendered video.

    Args:
        ffmpeg_bin: Path to ffmpeg binary.
        rendered_video: Path to the rendered visualization video.
        output_path: Final output path.
        intro_path: Optional intro video path.
        outro_path: Optional outro video path.
        intro_keep_audio: Whether to keep intro audio.
        outro_keep_audio: Whether to keep outro audio.
        target: Encoding target parameters.
        cancelled: Threading event to signal cancellation.
        progress_callback: Optional callback for progress (0.0-1.0).

    Returns:
        Path to the concatenated output.

    Raises:
        RuntimeError: If ffmpeg fails or export is cancelled.
    """
    if cancelled.is_set():
        raise RuntimeError("Export cancelled")

    # Build segment list
    segments: list[Path] = []
    keep_audio_flags: list[bool] = []
    has_audio_flags: list[bool] = []
    durations: list[float] = []

    if intro_path is not None:
        intro_info = probe_video_clip(intro_path)
        segments.append(intro_path)
        keep_audio_flags.append(intro_keep_audio)
        has_audio_flags.append(intro_info.has_audio)
        durations.append(intro_info.duration)

    # Rendered video always keeps audio
    rendered_info = probe_video_clip(rendered_video)
    segments.append(rendered_video)
    keep_audio_flags.append(True)
    has_audio_flags.append(rendered_info.has_audio)
    durations.append(rendered_info.duration)

    if outro_path is not None:
        outro_info = probe_video_clip(outro_path)
        segments.append(outro_path)
        keep_audio_flags.append(outro_keep_audio)
        has_audio_flags.append(outro_info.has_audio)
        durations.append(outro_info.duration)

    total_duration = sum(durations)

    # Use a temp dir for output to avoid read/write race on same file
    temp_dir = tempfile.mkdtemp(prefix="wavern_concat_")
    temp_output = Path(temp_dir) / f"concat.{target.container}"

    try:
        cmd = build_concat_cmd(
            ffmpeg_bin, segments, keep_audio_flags, has_audio_flags,
            target, temp_output,
        )
        logger.debug("Concat command: %s", cmd)

        if cancelled.is_set():
            raise RuntimeError("Export cancelled")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Drain stderr in background, parse progress
        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            assert proc.stderr is not None
            for raw_line in proc.stderr:
                line = raw_line.decode(errors="replace").strip()
                stderr_lines.append(line)
                if progress_callback and total_duration > 0:
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match:
                        h, m, s = match.groups()
                        elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                        progress = min(elapsed / total_duration, 1.0)
                        progress_callback(progress)

        drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
        drain_thread.start()

        # Wait for process, checking cancellation
        while proc.poll() is None:
            if cancelled.is_set():
                proc.kill()
                proc.wait()
                raise RuntimeError("Export cancelled")
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

        drain_thread.join(timeout=10)

        if proc.returncode != 0:
            stderr_output = "\n".join(stderr_lines[-50:])
            logger.error("Concat ffmpeg failed: %s", stderr_output)
            raise RuntimeError(f"Video concatenation failed: {stderr_output}")

        # Move result to final output
        shutil.move(str(temp_output), str(output_path))
        logger.info("Concat complete: %s", output_path)

        if progress_callback:
            progress_callback(1.0)

        return output_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

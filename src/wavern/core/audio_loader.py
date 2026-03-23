"""Audio file loading — soundfile primary, pydub fallback for mp3/aac."""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {".wav", ".flac", ".ogg", ".mp3", ".aac", ".m4a", ".wma"}


class AudioLoadError(Exception):
    """Raised when an audio file cannot be loaded or decoded."""


@dataclass(frozen=True)
class AudioMetadata:
    """Immutable metadata extracted from an audio file."""

    sample_rate: int
    duration: float
    num_channels: int
    num_samples: int
    file_path: str
    bitrate: int | None = None  # kbps, None if unknown


class AudioLoader:
    """Loads audio files into numpy arrays.

    Primary backend: soundfile (supports wav, flac, ogg).
    Fallback: pydub for mp3 and other ffmpeg-supported formats.
    """

    @staticmethod
    def load(file_path: str) -> tuple[NDArray[np.float32], AudioMetadata]:
        """Load audio file, return (mono_samples_float32, metadata).

        Always returns mono audio normalized to [-1.0, 1.0].

        Raises:
            AudioLoadError: If file cannot be read or format is unsupported.
        """
        path = Path(file_path)
        if not path.exists():
            raise AudioLoadError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise AudioLoadError(
                f"Unsupported format: {suffix}. Supported: {SUPPORTED_EXTENSIONS}"
            )

        try:
            audio, sr = AudioLoader._load_soundfile(file_path)
        except Exception:
            logger.info("soundfile failed for %s, trying pydub fallback", file_path, exc_info=True)
            try:
                audio, sr = AudioLoader._load_pydub_fallback(file_path)
            except Exception as e:
                raise AudioLoadError(f"Failed to load {file_path}: {e}") from e

        num_channels = 1
        if audio.ndim > 1:
            num_channels = audio.shape[1]
            audio = AudioLoader._to_mono(audio, num_channels)

        # Normalize to [-1.0, 1.0]
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val

        audio = audio.astype(np.float32)

        duration = len(audio) / sr
        bitrate = AudioLoader._probe_bitrate(file_path, duration)

        metadata = AudioMetadata(
            sample_rate=sr,
            duration=duration,
            num_channels=num_channels,
            num_samples=len(audio),
            file_path=file_path,
            bitrate=bitrate,
        )

        logger.info(
            "Loaded %s: %.1fs, %dHz, %d channels, %d samples, %s kbps",
            path.name,
            metadata.duration,
            sr,
            num_channels,
            len(audio),
            bitrate or "?",
        )

        return audio, metadata

    @staticmethod
    def _load_soundfile(file_path: str) -> tuple[NDArray[np.float32], int]:
        """Try loading with soundfile (libsndfile)."""
        import soundfile as sf

        audio, sr = sf.read(file_path, dtype="float32")
        return audio, sr

    @staticmethod
    def _load_pydub_fallback(file_path: str) -> tuple[NDArray[np.float32], int]:
        """Fallback for formats soundfile doesn't support (mp3, aac)."""
        from pydub import AudioSegment

        seg = AudioSegment.from_file(file_path)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        samples = samples / (2 ** (seg.sample_width * 8 - 1))

        if seg.channels > 1:
            samples = samples.reshape(-1, seg.channels)

        return samples, seg.frame_rate

    @staticmethod
    def _to_mono(audio: NDArray[np.float32], num_channels: int) -> NDArray[np.float32]:
        """Downmix multi-channel audio to mono by averaging."""
        if num_channels == 1:
            return audio.flatten()
        return np.mean(audio, axis=1).astype(np.float32)

    @staticmethod
    def _probe_bitrate(file_path: str, duration: float) -> int | None:
        """Extract audio bitrate in kbps. Tries ffprobe, falls back to file size estimate."""
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                result = subprocess.run(
                    [ffprobe, "-v", "quiet", "-print_format", "json",
                     "-show_format", file_path],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    br = info.get("format", {}).get("bit_rate")
                    if br is not None:
                        return int(br) // 1000
            except Exception:
                logger.debug("ffprobe bitrate extraction failed for %s", file_path)

        # Fallback: estimate from file size / duration
        if duration > 0:
            try:
                file_size_bytes = Path(file_path).stat().st_size
                return int(file_size_bytes * 8 / duration / 1000)
            except OSError:
                pass

        return None

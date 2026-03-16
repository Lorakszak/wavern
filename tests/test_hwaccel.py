"""Tests for hardware-accelerated encoder detection and mapping."""

import subprocess

import pytest

from wavern.core.hwaccel import (
    HW_ENCODER_MAP,
    HWAccelBackend,
    HWEncoder,
    build_hw_input_flags,
    clear_hw_cache,
    detect_hw_encoders,
    get_hw_encoder,
    map_quality_to_hw,
)


# Sample ffmpeg -encoders output snippets
_FFMPEG_OUTPUT_NVENC = b"""\
 V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC
 V..... libx265              libx265 H.265 / HEVC
 V..... h264_nvenc           NVIDIA NVENC H.264 encoder
 V..... hevc_nvenc           NVIDIA NVENC hevc encoder
 V..... av1_nvenc            NVIDIA NVENC av1 encoder
"""

_FFMPEG_OUTPUT_VAAPI = b"""\
 V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC
 V..... h264_vaapi           H.264/AVC (VAAPI)
 V..... hevc_vaapi           H.265/HEVC (VAAPI)
 V..... vp9_vaapi            VP9 (VAAPI)
"""

_FFMPEG_OUTPUT_MIXED = b"""\
 V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC
 V..... h264_nvenc           NVIDIA NVENC H.264 encoder
 V..... h264_vaapi           H.264/AVC (VAAPI)
 V..... h264_qsv             H.264/AVC (Intel Quick Sync Video)
"""

_FFMPEG_OUTPUT_NONE = b"""\
 V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC
 V..... libx265              libx265 H.265 / HEVC
 V..... libvpx-vp9           libvpx VP9
"""


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear HW encoder cache before and after each test."""
    clear_hw_cache()
    yield
    clear_hw_cache()


def _mock_subprocess(monkeypatch, stdout: bytes, returncode: int = 0):
    """Mock subprocess.run to return the given stdout."""
    def mock_run(*args, **kwargs):
        result = subprocess.CompletedProcess(args[0], returncode, stdout=stdout, stderr=b"")
        return result
    monkeypatch.setattr(subprocess, "run", mock_run)


class TestHWEncoderMap:
    def test_all_software_codecs_have_entries(self):
        assert "libx264" in HW_ENCODER_MAP
        assert "libx265" in HW_ENCODER_MAP
        assert "libaom-av1" in HW_ENCODER_MAP
        assert "libvpx-vp9" in HW_ENCODER_MAP

    def test_no_prores_or_gif(self):
        assert "prores_ks" not in HW_ENCODER_MAP
        assert "gif" not in HW_ENCODER_MAP

    def test_each_entry_has_valid_backend(self):
        for sw_codec, hw_list in HW_ENCODER_MAP.items():
            for hw in hw_list:
                assert isinstance(hw.backend, HWAccelBackend)
                assert hw.software_codec == sw_codec


class TestDetection:
    def test_detects_nvenc(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_NVENC)

        result = detect_hw_encoders()
        assert "libx264" in result
        assert result["libx264"].encoder_name == "h264_nvenc"
        assert result["libx264"].backend == HWAccelBackend.NVENC
        assert "libx265" in result
        assert result["libx265"].encoder_name == "hevc_nvenc"

    def test_detects_vaapi(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_VAAPI)

        result = detect_hw_encoders()
        assert "libx264" in result
        assert result["libx264"].encoder_name == "h264_vaapi"
        assert result["libx264"].backend == HWAccelBackend.VAAPI

    def test_no_hw_encoders(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_NONE)

        result = detect_hw_encoders()
        assert result == {}

    def test_priority_nvenc_over_vaapi(self, monkeypatch):
        """When both NVENC and VAAPI are available, NVENC should win."""
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_MIXED)

        result = detect_hw_encoders()
        assert result["libx264"].encoder_name == "h264_nvenc"
        assert result["libx264"].backend == HWAccelBackend.NVENC

    def test_caching(self, monkeypatch):
        """Second call should not invoke subprocess again."""
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        call_count = 0
        original_stdout = _FFMPEG_OUTPUT_NVENC

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(args[0], 0, stdout=original_stdout, stderr=b"")

        monkeypatch.setattr(subprocess, "run", mock_run)

        detect_hw_encoders()
        detect_hw_encoders()
        assert call_count == 1

    def test_clear_cache_forces_redetection(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(args[0], 0, stdout=_FFMPEG_OUTPUT_NVENC, stderr=b"")

        monkeypatch.setattr(subprocess, "run", mock_run)

        detect_hw_encoders()
        clear_hw_cache()
        detect_hw_encoders()
        assert call_count == 2

    def test_ffmpeg_not_found(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        result = detect_hw_encoders()
        assert result == {}

    def test_ffmpeg_failure(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, b"", returncode=1)
        result = detect_hw_encoders()
        assert result == {}


class TestGetHWEncoder:
    def test_hw_off_returns_none(self):
        assert get_hw_encoder("libx264", hw_accel="off") is None

    def test_needs_alpha_returns_none(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_NVENC)
        assert get_hw_encoder("libx264", hw_accel="auto", needs_alpha=True) is None

    def test_prores_no_hw(self):
        assert get_hw_encoder("prores_ks", hw_accel="auto") is None

    def test_gif_no_hw(self):
        assert get_hw_encoder("gif", hw_accel="auto") is None

    def test_auto_with_available_hw(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_NVENC)
        result = get_hw_encoder("libx264", hw_accel="auto")
        assert result is not None
        assert result.encoder_name == "h264_nvenc"

    def test_auto_fallback_no_hw(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")
        _mock_subprocess(monkeypatch, _FFMPEG_OUTPUT_NONE)
        assert get_hw_encoder("libx264", hw_accel="auto") is None


class TestQualityMapping:
    def test_nvenc_crf_to_cq(self):
        hw = HW_ENCODER_MAP["libx264"][0]  # h264_nvenc
        args = map_quality_to_hw(hw, crf=18, encoder_speed="medium")
        assert "-cq" in args
        assert "18" in args
        assert "-preset" in args
        assert "p4" in args  # medium → p4

    def test_vaapi_no_speed(self):
        # Find a VAAPI encoder
        vaapi_enc = None
        for hw in HW_ENCODER_MAP["libx264"]:
            if hw.backend == HWAccelBackend.VAAPI:
                vaapi_enc = hw
                break
        assert vaapi_enc is not None
        args = map_quality_to_hw(vaapi_enc, crf=23, encoder_speed="medium")
        assert "-qp" in args
        assert "23" in args
        assert "-preset" not in args

    def test_qsv_global_quality(self):
        qsv_enc = None
        for hw in HW_ENCODER_MAP["libx264"]:
            if hw.backend == HWAccelBackend.QSV:
                qsv_enc = hw
                break
        assert qsv_enc is not None
        args = map_quality_to_hw(qsv_enc, crf=18, encoder_speed="medium")
        assert "-global_quality" in args
        assert "18" in args
        assert "-preset" in args
        assert "medium" in args

    def test_nvenc_speed_mapping_slow(self):
        hw = HW_ENCODER_MAP["libx264"][0]  # h264_nvenc
        args = map_quality_to_hw(hw, crf=14, encoder_speed="slow")
        assert "p5" in args

    def test_nvenc_speed_mapping_ultrafast(self):
        hw = HW_ENCODER_MAP["libx264"][0]  # h264_nvenc
        args = map_quality_to_hw(hw, crf=35, encoder_speed="ultrafast")
        assert "p1" in args


class TestBuildHWInputFlags:
    def test_vaapi_includes_device_and_upload(self):
        vaapi_enc = None
        for hw in HW_ENCODER_MAP["libx264"]:
            if hw.backend == HWAccelBackend.VAAPI:
                vaapi_enc = hw
                break
        assert vaapi_enc is not None
        flags = build_hw_input_flags(vaapi_enc, "rgb24")
        assert "-vaapi_device" in flags
        assert "/dev/dri/renderD128" in flags
        assert "-vf" in flags
        assert "format=nv12,hwupload" in flags

    def test_nvenc_no_extra_flags(self):
        hw = HW_ENCODER_MAP["libx264"][0]  # h264_nvenc
        flags = build_hw_input_flags(hw, "rgb24")
        assert flags == []

    def test_qsv_no_extra_flags(self):
        """QSV with raw pipe input doesn't need special init flags."""
        qsv_enc = None
        for hw in HW_ENCODER_MAP["libx264"]:
            if hw.backend == HWAccelBackend.QSV:
                qsv_enc = hw
                break
        assert qsv_enc is not None
        flags = build_hw_input_flags(qsv_enc, "rgb24")
        assert flags == []

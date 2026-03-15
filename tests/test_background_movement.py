"""Tests for BackgroundMovement schema validation and serialization."""

import pytest
from pydantic import ValidationError

from wavern.presets.schema import BackgroundConfig, BackgroundMovement


class TestBackgroundMovement:
    def test_defaults(self):
        mv = BackgroundMovement()
        assert mv.type == "none"
        assert mv.speed == 1.0
        assert mv.intensity == 0.5
        assert mv.angle == 0.0
        assert mv.clamp_to_frame is False

    def test_valid_types(self):
        for t in ("none", "drift", "shake", "wave", "zoom_pulse", "breathe"):
            mv = BackgroundMovement(type=t)
            assert mv.type == t

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            BackgroundMovement(type="spin")

    def test_speed_bounds(self):
        BackgroundMovement(speed=0.0)
        BackgroundMovement(speed=10.0)
        with pytest.raises(ValidationError):
            BackgroundMovement(speed=-0.1)
        with pytest.raises(ValidationError):
            BackgroundMovement(speed=10.1)

    def test_intensity_bounds(self):
        BackgroundMovement(intensity=0.0)
        BackgroundMovement(intensity=2.0)
        with pytest.raises(ValidationError):
            BackgroundMovement(intensity=-0.1)
        with pytest.raises(ValidationError):
            BackgroundMovement(intensity=2.1)

    def test_angle_bounds(self):
        BackgroundMovement(angle=0.0)
        BackgroundMovement(angle=360.0)
        with pytest.raises(ValidationError):
            BackgroundMovement(angle=-1.0)
        with pytest.raises(ValidationError):
            BackgroundMovement(angle=361.0)

    def test_clamp_to_frame(self):
        mv = BackgroundMovement(type="shake", clamp_to_frame=True)
        assert mv.clamp_to_frame is True

    def test_serialization_roundtrip(self):
        mv = BackgroundMovement(
            type="drift", speed=3.0, intensity=1.5, angle=45.0, clamp_to_frame=True,
        )
        data = mv.model_dump()
        restored = BackgroundMovement(**data)
        assert restored.type == "drift"
        assert restored.speed == 3.0
        assert restored.intensity == 1.5
        assert restored.angle == 45.0
        assert restored.clamp_to_frame is True

    def test_background_config_has_movement(self):
        bg = BackgroundConfig()
        assert bg.movement.type == "none"

    def test_background_config_with_movement(self):
        bg = BackgroundConfig(
            type="image",
            image_path="/some/image.png",
            movement=BackgroundMovement(type="wave", speed=2.0),
        )
        assert bg.movement.type == "wave"
        assert bg.movement.speed == 2.0

    def test_video_background_type(self):
        bg = BackgroundConfig(type="video", video_path="/some/video.mp4")
        assert bg.type == "video"
        assert bg.video_path == "/some/video.mp4"


class TestBackgroundTransform:
    def test_defaults(self):
        bg = BackgroundConfig()
        assert bg.rotation == 0.0
        assert bg.mirror_x is False
        assert bg.mirror_y is False

    def test_rotation_bounds(self):
        BackgroundConfig(rotation=0.0)
        BackgroundConfig(rotation=360.0)
        with pytest.raises(ValidationError):
            BackgroundConfig(rotation=-1.0)
        with pytest.raises(ValidationError):
            BackgroundConfig(rotation=361.0)

    def test_mirror_flags(self):
        bg = BackgroundConfig(mirror_x=True, mirror_y=True)
        assert bg.mirror_x is True
        assert bg.mirror_y is True

    def test_transform_roundtrip(self):
        bg = BackgroundConfig(
            type="image",
            image_path="/img.png",
            rotation=90.0,
            mirror_x=True,
            mirror_y=False,
        )
        data = bg.model_dump()
        restored = BackgroundConfig(**data)
        assert restored.rotation == 90.0
        assert restored.mirror_x is True
        assert restored.mirror_y is False

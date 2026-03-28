"""Tests for wavern.presets.schema.BackgroundMovement and BackgroundMovements.

WHAT THIS TESTS:
- BackgroundMovement field defaults and bounds (enabled, speed, intensity, angle, clamp_to_frame)
- BackgroundMovements container: all 5 movement types as named fields
- BackgroundConfig.movements field integration
- Serialization round-trip preserves all values
Does NOT test: actual background rendering or pixel output (those are renderer-level concerns)
"""

import pytest
from pydantic import ValidationError

from wavern.presets.manager import _migrate_preset_data
from wavern.presets.schema import BackgroundConfig, BackgroundMovement, BackgroundMovements


class TestBackgroundMovement:
    def test_defaults(self):
        mv = BackgroundMovement()
        assert mv.enabled is False
        assert mv.speed == 1.0
        assert mv.intensity == 0.5
        assert mv.angle == 0.0
        assert mv.clamp_to_frame is False
        assert mv.audio.enabled is False

    def test_enabled(self):
        mv = BackgroundMovement(enabled=True)
        assert mv.enabled is True

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
        mv = BackgroundMovement(enabled=True, clamp_to_frame=True)
        assert mv.clamp_to_frame is True

    def test_serialization_roundtrip(self):
        mv = BackgroundMovement(
            enabled=True,
            speed=3.0,
            intensity=1.5,
            angle=45.0,
            clamp_to_frame=True,
        )
        data = mv.model_dump()
        restored = BackgroundMovement(**data)
        assert restored.enabled is True
        assert restored.speed == 3.0
        assert restored.intensity == 1.5
        assert restored.angle == 45.0
        assert restored.clamp_to_frame is True


class TestBackgroundMovements:
    def test_defaults(self):
        movements = BackgroundMovements()
        assert movements.drift.enabled is False
        assert movements.shake.enabled is False
        assert movements.wave.enabled is False
        assert movements.zoom_pulse.enabled is False
        assert movements.breathe.enabled is False

    def test_individual_enable(self):
        movements = BackgroundMovements(
            drift=BackgroundMovement(enabled=True, speed=0.3, angle=90.0),
        )
        assert movements.drift.enabled is True
        assert movements.drift.speed == 0.3
        assert movements.drift.angle == 90.0
        assert movements.shake.enabled is False

    def test_multiple_enable(self):
        movements = BackgroundMovements(
            drift=BackgroundMovement(enabled=True, speed=0.5),
            wave=BackgroundMovement(enabled=True, intensity=1.0),
            breathe=BackgroundMovement(enabled=True, speed=2.0),
        )
        assert movements.drift.enabled is True
        assert movements.wave.enabled is True
        assert movements.breathe.enabled is True
        assert movements.shake.enabled is False
        assert movements.zoom_pulse.enabled is False

    def test_serialization_roundtrip(self):
        movements = BackgroundMovements(
            drift=BackgroundMovement(enabled=True, speed=0.3, angle=90.0),
            shake=BackgroundMovement(enabled=True, intensity=0.8),
        )
        data = movements.model_dump()
        restored = BackgroundMovements(**data)
        assert restored.drift.enabled is True
        assert restored.drift.angle == 90.0
        assert restored.shake.enabled is True
        assert restored.shake.intensity == 0.8


class TestBackgroundConfigMovements:
    def test_has_movements(self):
        bg = BackgroundConfig()
        assert bg.movements.drift.enabled is False

    def test_with_movements(self):
        bg = BackgroundConfig(
            type="image",
            image_path="/some/image.png",
            movements=BackgroundMovements(
                wave=BackgroundMovement(enabled=True, speed=2.0),
            ),
        )
        assert bg.movements.wave.enabled is True
        assert bg.movements.wave.speed == 2.0


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


class TestMovementMigration:
    def test_old_single_movement_migrated(self):
        """Old format: movement.type selects which movement is active."""
        raw = {
            "name": "Test",
            "layers": [{"visualization_type": "bars", "params": {}}],
            "background": {
                "type": "image",
                "movement": {
                    "type": "drift",
                    "speed": 0.3,
                    "intensity": 0.2,
                    "angle": 90.0,
                    "clamp_to_frame": False,
                },
            },
        }
        migrated = _migrate_preset_data(raw)
        movements = migrated["background"]["movements"]
        assert movements["drift"]["enabled"] is True
        assert movements["drift"]["speed"] == 0.3
        assert movements["drift"]["angle"] == 90.0
        assert "shake" not in movements

    def test_old_none_movement_migrated(self):
        """Old format with type=none should produce empty movements."""
        raw = {
            "name": "Test",
            "layers": [{"visualization_type": "bars", "params": {}}],
            "background": {
                "type": "solid",
                "movement": {"type": "none"},
            },
        }
        migrated = _migrate_preset_data(raw)
        bg = migrated["background"]
        assert "movement" not in bg

    def test_new_format_untouched(self):
        """New format with 'movements' key should not be modified."""
        raw = {
            "name": "Test",
            "layers": [{"visualization_type": "bars", "params": {}}],
            "background": {
                "type": "image",
                "movements": {
                    "drift": {"enabled": True, "speed": 0.5},
                    "wave": {"enabled": True, "intensity": 1.0},
                },
            },
        }
        migrated = _migrate_preset_data(raw)
        assert migrated["background"]["movements"]["drift"]["enabled"] is True
        assert migrated["background"]["movements"]["wave"]["enabled"] is True

    def test_no_background_untouched(self):
        """Preset with no background section should pass through."""
        raw = {
            "name": "Test",
            "layers": [{"visualization_type": "bars", "params": {}}],
        }
        migrated = _migrate_preset_data(raw)
        assert "background" not in migrated

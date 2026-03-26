"""Tests for wavern.presets.schema.

WHAT THIS TESTS:
- Preset constructs with minimal and full field sets; JSON round-trip preserves all values
- ValidationError raised for empty name and out-of-range fft_size
- BackgroundConfig, ColorStop, VideoOverlayConfig field defaults and validation
- Preset round-trip including BackgroundMovement, transform fields, and VideoOverlayConfig
Does NOT test: preset file I/O or the PresetManager (see test_preset_manager)
"""


import pytest
from pydantic import ValidationError

from wavern.presets.schema import (
    AudioReactiveConfig,
    BackgroundConfig,
    BackgroundEffect,
    BackgroundEffects,
    BackgroundMovement,
    BlendMode,
    ChromaticAberrationEffect,
    ColorStop,
    FilmGrainEffect,
    GlobalEffects,
    GlitchEffect,
    OverlayBlendMode,
    Preset,
    VideoOverlayConfig,
    VignetteEffect,
    VisualizationLayer,
)


class TestPresetSchema:
    def test_minimal_preset(self):
        preset = Preset(
            name="Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        assert preset.name == "Test"
        assert preset.fps == 60
        assert preset.fft_size == 2048

    def test_full_preset(self):
        preset = Preset(
            name="Full Test",
            description="A complete preset",
            author="tester",
            layers=[
                VisualizationLayer(
                    visualization_type="waveform",
                    params={"line_thickness": 3.0},
                    blend_mode=BlendMode.ADDITIVE,
                ),
            ],
            color_palette=["#FF0000", "#00FF00"],
            background=BackgroundConfig(type="solid", color="#111111"),
            fft_size=4096,
            smoothing=0.5,
            fps=30,
        )
        assert preset.author == "tester"
        assert preset.layers[0].params["line_thickness"] == 3.0

    def test_json_roundtrip(self):
        preset = Preset(
            name="Roundtrip",
            layers=[
                VisualizationLayer(
                    visualization_type="particles",
                    params={"max_particles": 5000},
                ),
            ],
        )
        json_str = preset.model_dump_json()
        loaded = Preset.model_validate_json(json_str)
        assert loaded.name == "Roundtrip"
        assert loaded.layers[0].params["max_particles"] == 5000

    def test_invalid_name_empty(self):
        with pytest.raises(ValidationError):
            Preset(
                name="",
                layers=[VisualizationLayer(visualization_type="waveform")],
            )

    def test_invalid_fft_size(self):
        with pytest.raises(ValidationError):
            Preset(
                name="Bad FFT",
                layers=[VisualizationLayer(visualization_type="waveform")],
                fft_size=100,  # below minimum 256
            )

    def test_color_stop_validation(self):
        stop = ColorStop(position=0.5, color="#FF00AA")
        assert stop.position == 0.5

        with pytest.raises(ValidationError):
            ColorStop(position=1.5, color="#FF00AA")

    def test_background_config_defaults(self):
        bg = BackgroundConfig()
        assert bg.type == "solid"
        assert bg.color == "#000000"
        assert bg.opacity == 1.0
        assert bg.movement.type == "none"

    def test_video_overlay_defaults(self):
        ov = VideoOverlayConfig()
        assert ov.enabled is False
        assert ov.video_path is None
        assert ov.blend_mode == OverlayBlendMode.ADDITIVE
        assert ov.opacity == 1.0
        assert ov.rotation == 0.0
        assert ov.mirror_x is False
        assert ov.mirror_y is False

    def test_preset_has_video_overlay(self):
        preset = Preset(
            name="Overlay Test",
            layers=[VisualizationLayer(visualization_type="waveform")],
            video_overlay=VideoOverlayConfig(
                enabled=True,
                video_path="/tmp/particles.webm",
                blend_mode=OverlayBlendMode.SCREEN,
                opacity=0.8,
            ),
        )
        assert preset.video_overlay.enabled is True
        assert preset.video_overlay.blend_mode == OverlayBlendMode.SCREEN

    def test_preset_roundtrip_with_new_fields(self):
        preset = Preset(
            name="Full",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            background=BackgroundConfig(
                type="video",
                video_path="/tmp/bg.mp4",
                rotation=180.0,
                mirror_x=True,
                movement=BackgroundMovement(
                    type="drift", speed=2.0, angle=90.0, clamp_to_frame=True,
                ),
            ),
            video_overlay=VideoOverlayConfig(
                enabled=True, opacity=0.5,
                rotation=90.0, mirror_x=True, mirror_y=True,
            ),
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.background.type == "video"
        assert restored.background.rotation == 180.0
        assert restored.background.mirror_x is True
        assert restored.background.movement.type == "drift"
        assert restored.background.movement.angle == 90.0
        assert restored.background.movement.clamp_to_frame is True
        assert restored.video_overlay.enabled is True
        assert restored.video_overlay.opacity == 0.5
        assert restored.video_overlay.rotation == 90.0
        assert restored.video_overlay.mirror_x is True
        assert restored.video_overlay.mirror_y is True


class TestAudioReactiveConfig:
    def test_defaults(self):
        arc = AudioReactiveConfig()
        assert arc.enabled is False
        assert arc.source == "amplitude"
        assert arc.sensitivity == 1.0

    def test_valid_sources(self):
        for source in ("amplitude", "bass", "beat", "mid", "treble"):
            arc = AudioReactiveConfig(source=source)
            assert arc.source == source

    def test_invalid_source(self):
        with pytest.raises(ValidationError):
            AudioReactiveConfig(source="invalid_source")

    def test_sensitivity_range(self):
        AudioReactiveConfig(sensitivity=0.1)  # min
        AudioReactiveConfig(sensitivity=5.0)  # max
        with pytest.raises(ValidationError):
            AudioReactiveConfig(sensitivity=0.0)
        with pytest.raises(ValidationError):
            AudioReactiveConfig(sensitivity=6.0)


class TestBackgroundEffect:
    def test_defaults(self):
        effect = BackgroundEffect()
        assert effect.enabled is False
        assert effect.intensity == 0.5
        assert effect.audio.enabled is False

    def test_full_construction(self):
        effect = BackgroundEffect(
            enabled=True,
            intensity=0.8,
            audio=AudioReactiveConfig(enabled=True, source="bass", sensitivity=2.0),
        )
        assert effect.enabled is True
        assert effect.intensity == 0.8
        assert effect.audio.source == "bass"

    def test_intensity_range(self):
        BackgroundEffect(intensity=0.0)
        BackgroundEffect(intensity=1.0)
        with pytest.raises(ValidationError):
            BackgroundEffect(intensity=-0.1)
        with pytest.raises(ValidationError):
            BackgroundEffect(intensity=1.1)


class TestBackgroundEffects:
    def test_defaults(self):
        effects = BackgroundEffects()
        assert effects.blur.enabled is False
        assert effects.hue_shift.enabled is False
        assert effects.saturation.enabled is False
        assert effects.brightness.enabled is False

    def test_individual_effect_enabled(self):
        effects = BackgroundEffects(
            blur=BackgroundEffect(enabled=True, intensity=0.7),
        )
        assert effects.blur.enabled is True
        assert effects.blur.intensity == 0.7
        assert effects.hue_shift.enabled is False


class TestBackgroundSchemaBackwardCompat:
    def test_old_movement_without_audio(self):
        """Old preset JSON without audio key loads with defaults."""
        data = {"type": "drift", "speed": 2.0, "intensity": 0.5, "angle": 90.0, "clamp_to_frame": False}
        movement = BackgroundMovement.model_validate(data)
        assert movement.audio.enabled is False
        assert movement.audio.source == "amplitude"

    def test_old_background_without_effects(self):
        """Old preset JSON without effects key loads with defaults."""
        data = {"type": "solid", "color": "#000000"}
        bg = BackgroundConfig.model_validate(data)
        assert bg.effects.blur.enabled is False
        assert bg.effects.hue_shift.enabled is False

    def test_preset_roundtrip_with_effects(self):
        preset = Preset(
            name="Effects Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            background=BackgroundConfig(
                type="image",
                image_path="/tmp/bg.png",
                movement=BackgroundMovement(
                    type="shake",
                    audio=AudioReactiveConfig(enabled=True, source="beat", sensitivity=1.5),
                ),
                effects=BackgroundEffects(
                    blur=BackgroundEffect(enabled=True, intensity=0.7),
                    brightness=BackgroundEffect(
                        enabled=True,
                        intensity=0.3,
                        audio=AudioReactiveConfig(enabled=True, source="bass"),
                    ),
                ),
            ),
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.background.movement.audio.enabled is True
        assert restored.background.movement.audio.source == "beat"
        assert restored.background.effects.blur.enabled is True
        assert restored.background.effects.blur.intensity == 0.7
        assert restored.background.effects.brightness.audio.source == "bass"


class TestVignetteEffect:
    def test_defaults(self):
        v = VignetteEffect()
        assert v.enabled is False
        assert v.intensity == 0.5
        assert v.shape == "circular"
        assert v.audio.enabled is False

    def test_valid_shapes(self):
        for shape in ("circular", "rectangular", "diamond"):
            v = VignetteEffect(shape=shape)
            assert v.shape == shape

    def test_invalid_shape(self):
        with pytest.raises(ValidationError):
            VignetteEffect(shape="triangle")

    def test_intensity_range(self):
        VignetteEffect(intensity=0.0)
        VignetteEffect(intensity=1.0)
        with pytest.raises(ValidationError):
            VignetteEffect(intensity=-0.1)
        with pytest.raises(ValidationError):
            VignetteEffect(intensity=1.1)


class TestChromaticAberrationEffect:
    def test_defaults(self):
        c = ChromaticAberrationEffect()
        assert c.enabled is False
        assert c.intensity == 0.5
        assert c.direction == "radial"
        assert c.angle == 0.0

    def test_valid_directions(self):
        for direction in ("radial", "linear"):
            c = ChromaticAberrationEffect(direction=direction)
            assert c.direction == direction

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(direction="spiral")

    def test_angle_range(self):
        ChromaticAberrationEffect(angle=0.0)
        ChromaticAberrationEffect(angle=360.0)
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(angle=-1.0)
        with pytest.raises(ValidationError):
            ChromaticAberrationEffect(angle=361.0)

    def test_full_construction(self):
        c = ChromaticAberrationEffect(
            enabled=True,
            intensity=0.8,
            direction="linear",
            angle=45.0,
            audio=AudioReactiveConfig(enabled=True, source="treble"),
        )
        assert c.direction == "linear"
        assert c.angle == 45.0
        assert c.audio.source == "treble"


class TestGlitchEffect:
    def test_defaults(self):
        g = GlitchEffect()
        assert g.enabled is False
        assert g.intensity == 0.5
        assert g.type == "scanline"

    def test_valid_types(self):
        for t in ("scanline", "block", "digital"):
            g = GlitchEffect(type=t)
            assert g.type == t

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            GlitchEffect(type="vhs")


class TestFilmGrainEffect:
    def test_defaults(self):
        f = FilmGrainEffect()
        assert f.enabled is False
        assert f.intensity == 0.5
        assert f.audio.enabled is False

    def test_intensity_range(self):
        FilmGrainEffect(intensity=0.0)
        FilmGrainEffect(intensity=1.0)
        with pytest.raises(ValidationError):
            FilmGrainEffect(intensity=-0.1)
        with pytest.raises(ValidationError):
            FilmGrainEffect(intensity=1.1)


class TestGlobalEffects:
    def test_defaults(self):
        ge = GlobalEffects()
        assert ge.apply_stage == "before_overlays"
        assert ge.vignette.enabled is False
        assert ge.chromatic_aberration.enabled is False
        assert ge.glitch.enabled is False
        assert ge.film_grain.enabled is False

    def test_valid_apply_stages(self):
        for stage in ("before_overlays", "after_overlays"):
            ge = GlobalEffects(apply_stage=stage)
            assert ge.apply_stage == stage

    def test_invalid_apply_stage(self):
        with pytest.raises(ValidationError):
            GlobalEffects(apply_stage="during_overlays")

    def test_individual_effect_enabled(self):
        ge = GlobalEffects(
            glitch=GlitchEffect(enabled=True, intensity=0.7, type="block"),
        )
        assert ge.glitch.enabled is True
        assert ge.glitch.type == "block"
        assert ge.vignette.enabled is False


class TestGlobalEffectsBackwardCompat:
    def test_old_preset_without_global_effects(self):
        """Old preset JSON without global_effects loads with defaults."""
        preset = Preset(
            name="Legacy Preset",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
        )
        assert preset.global_effects.apply_stage == "before_overlays"
        assert preset.global_effects.vignette.enabled is False
        assert preset.global_effects.glitch.enabled is False

    def test_preset_roundtrip_with_global_effects(self):
        preset = Preset(
            name="Global FX Test",
            layers=[VisualizationLayer(visualization_type="spectrum_bars")],
            global_effects=GlobalEffects(
                apply_stage="after_overlays",
                vignette=VignetteEffect(enabled=True, intensity=0.8, shape="diamond"),
                chromatic_aberration=ChromaticAberrationEffect(
                    enabled=True, direction="linear", angle=90.0,
                    audio=AudioReactiveConfig(enabled=True, source="treble", sensitivity=2.0),
                ),
                glitch=GlitchEffect(enabled=True, type="digital"),
                film_grain=FilmGrainEffect(enabled=True, intensity=0.3),
            ),
        )
        json_str = preset.model_dump_json()
        restored = Preset.model_validate_json(json_str)
        assert restored.global_effects.apply_stage == "after_overlays"
        assert restored.global_effects.vignette.shape == "diamond"
        assert restored.global_effects.chromatic_aberration.direction == "linear"
        assert restored.global_effects.chromatic_aberration.angle == 90.0
        assert restored.global_effects.chromatic_aberration.audio.source == "treble"
        assert restored.global_effects.glitch.type == "digital"
        assert restored.global_effects.film_grain.intensity == 0.3

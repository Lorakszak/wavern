# wavern/core — Agent Guide

## Purpose
Display-agnostic processing layer. No Qt imports anywhere in this directory.

## Module Inventory
| File | Responsibility |
|---|---|
| `audio_loader.py` | Load audio files → numpy array + metadata |
| `audio_analyzer.py` | FFT, beat detection → `FrameAnalysis` dataclass |
| `audio_player.py` | Playback via sounddevice |
| `timeline.py` | Frame↔time conversion for a fixed fps |
| `renderer.py` | Per-frame GPU orchestration (bg → viz → overlay → text) |
| `video_source.py` | PyAV video decoding for backgrounds/overlays |
| `text_overlay.py` | FreeType text rasterization into OpenGL texture |
| `font_manager.py` | System font discovery and caching |
| `export_config.py` | `ExportConfig` dataclass (shared between export and ffmpeg_cmd) |
| `export.py` | `ExportPipeline` — headless render loop + ffmpeg mux |
| `ffmpeg_cmd.py` | Pure function: build ffmpeg CLI args from `ExportConfig` |
| `gif_export.py` | Two-pass GIF pipeline (palette gen + dither) |
| `codecs.py` | Codec descriptors, container→codec mapping, quality presets |
| `hwaccel.py` | HW encoder detection (NVENC, VAAPI, VideoToolbox) |

## Key Contract: FrameAnalysis
`AudioAnalyzer.analyze_frame(timestamp) -> FrameAnalysis` is the universal audio
contract. All visualizations receive it — never pass raw audio arrays to render methods.

## Renderer is Display-Agnostic
`Renderer.render_frame(frame_analysis, fbo, resolution)` works identically for:
- GUI preview: called from `GLWidget` with a Qt FBO
- Headless export: called from `ExportPipeline` with a standalone moderngl FBO

Never add Qt imports or GUI awareness to any file in this directory.

## Background Effects on All Background Types
Background effects (blur, hue_shift, saturation, brightness, pixelate, posterize, invert) work on all background types. For image/video/gradient backgrounds, the renderer renders the background quad to an intermediate FBO, then applies effects in a second pass (`_render_bg_quad`). For solid/none backgrounds (no texture), `_apply_bg_effects_standalone()` copies the already-cleared FBO to the intermediate and runs the effects shader on it.

## Global Effects Apply Stage
Global effects can be applied `"before_overlays"` or `"after_overlays"`. Both use the same `_apply_global_effects()` method and shader — the staging only controls when in the pipeline the pass runs.

## Logging Pattern
All core modules use `logger = logging.getLogger(__name__)`. Never use `print()` or `logging.basicConfig()`. The centralized setup in `src/wavern/logging_setup.py` handles handler configuration.

## Safe Uniform Setting
GLSL compilers strip unused uniforms. Always use:
- `self._set_uniform(prog, name, value)` — sets a scalar/vector uniform safely
- `self._write_uniform(prog, name, data)` — writes a numpy buffer

Never use `prog["name"].value = x` directly — raises `KeyError` if the uniform was optimised out.

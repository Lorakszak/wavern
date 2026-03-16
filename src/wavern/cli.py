"""CLI interface for Wavern — GUI launch and headless rendering."""

import logging
import sys
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="wavern")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Wavern — highly customizable local music visualizer."""
    if ctx.invoked_subcommand is None:
        # Default to GUI
        ctx.invoke(gui)


@cli.command()
@click.argument("audio_file", required=False, type=click.Path(exists=True, path_type=Path))
@click.option("-p", "--preset", default=None, help="Preset name to load on startup")
def gui(audio_file: Path | None = None, preset: str | None = None) -> None:
    """Launch the GUI (default command)."""
    from wavern.app import run_gui

    sys.exit(run_gui(audio_path=audio_file, preset_name=preset))


@cli.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("-p", "--preset", required=True, help="Preset name or path to .json file")
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path), help="Output video path")
@click.option("-r", "--resolution", default="1920x1080", help="Resolution WxH")
@click.option("--fps", default=60, type=int, help="Frames per second")
@click.option("--codec", default=None, help="Video codec (default: auto based on format)")
@click.option("--crf", default=None, type=int, help="Quality 0-51, lower=better (overrides --quality)")
@click.option(
    "--format", "container", default="mp4",
    type=click.Choice(["mp4", "webm", "mov", "gif"]),
)
@click.option(
    "--quality", "quality_preset", default="high",
    type=click.Choice(["highest", "very_high", "high", "medium", "low", "lowest", "custom"]),
    help="Quality preset (default: high)",
)
@click.option("--encoder-speed", default=None, help="Encoder speed (only with --quality custom)")
@click.option(
    "--audio-bitrate", default="192k",
    type=click.Choice(["128k", "192k", "256k", "320k"]),
    help="Audio bitrate (default: 192k)",
)
@click.option("--gif-colors", default=256, type=int, help="GIF max colors (64-256)")
@click.option("--gif-no-dither", is_flag=True, help="Disable GIF dithering")
@click.option("--gif-loop", default=0, type=int, help="GIF loop count (0=infinite)")
@click.option("--gif-scale", default=1.0, type=float, help="GIF scale factor (0.25-1.0)")
@click.option(
    "--hw-accel", default="auto",
    type=click.Choice(["auto", "off"]),
    help="Hardware acceleration: auto detects GPU encoders, off uses CPU (default: auto)",
)
def render(
    audio_file: Path,
    preset: str,
    output: Path,
    resolution: str,
    fps: int,
    codec: str | None,
    crf: int | None,
    container: str,
    quality_preset: str,
    encoder_speed: str | None,
    audio_bitrate: str,
    gif_colors: int,
    gif_no_dither: bool,
    gif_loop: int,
    gif_scale: float,
    hw_accel: str,
) -> None:
    """Render a visualization to video (headless, no GUI)."""
    import wavern.visualizations  # noqa: F401
    from wavern.core.codecs import get_default_codec, get_quality_settings
    from wavern.core.export import ExportConfig, ExportPipeline
    from wavern.presets.manager import PresetManager

    # Parse resolution
    try:
        w, h = resolution.split("x")
        res = (int(w), int(h))
    except ValueError:
        click.echo(f"Invalid resolution: {resolution}. Use WxH format (e.g. 1920x1080).")
        sys.exit(1)

    # Auto-select codec
    if codec is None:
        codec = get_default_codec(container)

    # Resolve quality settings
    if quality_preset != "custom":
        quality = get_quality_settings(quality_preset, codec)
        resolved_crf = quality.get("crf", 18)
        resolved_speed = quality.get("encoder_speed", "medium")
        resolved_prores = quality.get("prores_profile", 3)
    else:
        resolved_crf = crf if crf is not None else 18
        resolved_speed = encoder_speed if encoder_speed is not None else "medium"
        resolved_prores = 3

    # CLI --crf overrides preset CRF
    if crf is not None:
        resolved_crf = crf

    # Load preset
    manager = PresetManager()
    preset_path = Path(preset)
    if preset_path.exists() and preset_path.suffix == ".json":
        loaded_preset = manager.load_from_path(preset_path)
    else:
        loaded_preset = manager.load(preset)

    config = ExportConfig(
        output_path=output,
        resolution=res,
        fps=fps,
        video_codec=codec,
        container=container,
        crf=resolved_crf,
        encoder_speed=resolved_speed,
        quality_preset=quality_preset,
        audio_bitrate=audio_bitrate,
        prores_profile=resolved_prores,
        gif_max_colors=gif_colors,
        gif_dither=not gif_no_dither,
        gif_loop=gif_loop,
        gif_scale=gif_scale,
        hw_accel=hw_accel,
    )

    click.echo(f"Rendering: {audio_file.name}")
    click.echo(f"Preset: {loaded_preset.name}")
    click.echo(f"Output: {output} ({res[0]}x{res[1]}, {fps}fps, {codec})")
    click.echo(f"Quality: {quality_preset} (CRF {resolved_crf})")
    click.echo(f"HW Accel: {hw_accel}")

    def progress_callback(progress: float) -> None:
        bar_width = 40
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        click.echo(f"\r  [{bar}] {progress * 100:.0f}%", nl=False)

    pipeline = ExportPipeline(
        audio_path=audio_file,
        preset=loaded_preset,
        export_config=config,
        progress_callback=progress_callback,
    )

    try:
        pipeline.run()
        click.echo(f"\nDone: {output}")
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@cli.command("list-presets")
def list_presets() -> None:
    """List all available visualization presets."""
    from wavern.presets.manager import PresetManager

    manager = PresetManager()
    presets = manager.list_presets()

    if not presets:
        click.echo("No presets found.")
        return

    click.echo(f"{'Name':<30} {'Source':<10}")
    click.echo("-" * 40)
    for p in presets:
        click.echo(f"{p['name']:<30} {p['source']:<10}")


@cli.command("list-visualizations")
def list_visualizations() -> None:
    """List all registered visualization types."""
    import wavern.visualizations  # noqa: F401
    from wavern.visualizations.registry import VisualizationRegistry

    registry = VisualizationRegistry()
    vizs = registry.list_all()

    if not vizs:
        click.echo("No visualizations registered.")
        return

    click.echo(f"{'Name':<25} {'Display Name':<25} {'Category':<15}")
    click.echo("-" * 65)
    for v in vizs:
        click.echo(f"{v['name']:<25} {v['display_name']:<25} {v['category']:<15}")

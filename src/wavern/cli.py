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
@click.option("--crf", default=18, type=int, help="Quality 0-51, lower=better")
@click.option("--format", "container", default="mp4", type=click.Choice(["mp4", "webm"]))
def render(
    audio_file: Path,
    preset: str,
    output: Path,
    resolution: str,
    fps: int,
    codec: str | None,
    crf: int,
    container: str,
) -> None:
    """Render a visualization to video (headless, no GUI)."""
    # Import here to avoid loading Qt for headless mode
    import wavern.visualizations  # noqa: F401
    from wavern.core.export import ExportConfig, ExportPipeline
    from wavern.presets.manager import PresetManager
    from wavern.presets.schema import Preset

    # Parse resolution
    try:
        w, h = resolution.split("x")
        res = (int(w), int(h))
    except ValueError:
        click.echo(f"Invalid resolution: {resolution}. Use WxH format (e.g. 1920x1080).")
        sys.exit(1)

    # Auto-select codec
    if codec is None:
        codec = "libx264" if container == "mp4" else "libvpx-vp9"

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
        crf=crf,
    )

    click.echo(f"Rendering: {audio_file.name}")
    click.echo(f"Preset: {loaded_preset.name}")
    click.echo(f"Output: {output} ({res[0]}x{res[1]}, {fps}fps, {codec})")

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

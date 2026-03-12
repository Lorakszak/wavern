# Wavern - Local Music Visualizer

<p align="center">
  <img src="assets/logo.jpeg" alt="Wavern logo" width="320"/>
</p>

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet)](https://docs.astral.sh/uv/)

Highly customizable local music visualizer with real-time GPU-accelerated preview, preset system, and video export.

## Features

- **Real-time preview** — OpenGL 3.3+ GPU-accelerated visualization synced to audio playback
- **5 built-in visualizations** — Spectrum Bars, Classic Waveform, Circular Spectrum, Particle Burst, Smoky Waves
- **Full parameter control** — every visualization exposes tunable parameters (bar count, speed, thickness, etc.) with live preview
- **Color palettes** — multi-color gradients applied across visualizations
- **Preset system** — save/load/share visualization configurations as JSON files
- **Transparent export** — render with no background for compositing (WebM/VP9 with alpha)
- **Headless CLI rendering** — batch export videos from presets without opening the GUI
- **Plugin system** — drop a Python file in `~/.config/wavern/plugins/` to add custom visualizations

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- ffmpeg (for video export)
- OpenGL 3.3+ capable GPU
- Linux with PulseAudio or PipeWire (for audio playback via sounddevice/PortAudio)

## Installation

```bash
git clone https://github.com/Lorakszak/wavern && cd wavern
uv sync
```

## Usage

### GUI

```bash
uv run wavern gui                          # launch empty
uv run wavern gui audio/song.mp3           # launch with audio file
uv run wavern gui song.mp3 --preset "Neon Spectrum"  # launch with preset
```

Import audio via **File > Import Audio** (Ctrl+O) or pass a file path as argument. Select presets from the sidebar, tweak parameters, colors, and background in the settings panel. Render via **File > Render Video** (Ctrl+E).

### Headless Video Export

```bash
uv run wavern render audio/song.mp3 \
  --preset "Neon Spectrum" \
  --output video/output.mp4 \
  --resolution 1920x1080 \
  --fps 60 \
  --crf 18
```

For transparent background (no background, just the visualization):

```bash
uv run wavern render audio/song.mp3 \
  --preset "My Preset" \
  --output video/output.webm \
  --format webm
```

### Other Commands

```bash
uv run wavern list-presets          # show all available presets
uv run wavern list-visualizations   # show registered visualization types
```

## Keyboard Shortcuts

### Playback & Transport

| Shortcut | Action |
|----------|--------|
| `Space` | Play / Pause |
| `Left` / `Right` | Seek ±5 seconds |
| `Home` | Go to start |

### File

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Import Audio |
| `Ctrl+E` | Render Video |
| `Ctrl+S` | Save Preset |
| `Ctrl+Shift+S` | Save Preset As… |
| `Ctrl+Q` | Quit |

### View

| Shortcut | Action |
|----------|--------|
| `Ctrl+B` | Toggle Sidebar |
| `F11` | Toggle Fullscreen |

### Visualization

| Shortcut | Action |
|----------|--------|
| `Ctrl+1` | Switch to Spectrum Bars |
| `Ctrl+2` | Switch to Classic Waveform |
| `Ctrl+3` | Switch to Circular Spectrum |
| `Ctrl+4` | Switch to Particle Burst |
| `Ctrl+5` | Switch to Smoky Waves |

## Built-in Visualizations

| Name | Description |
|------|-------------|
| Spectrum Bars | Classic vertical bar spectrum analyzer with logarithmic frequency binning |
| Classic Waveform | Audio waveform as a line or filled shape |
| Circular Spectrum | Radial bars arranged around a rotating circle |
| Particle Burst | Audio-reactive particle system with burst effects on beats |
| Smoky Waves | Layered sinusoidal waves with audio-reactive turbulence |

## Presets

Built-in presets ship with the package. Custom presets are saved to `~/.config/wavern/presets/` as JSON files. Use the **Save** button in the GUI or copy preset JSON files directly.

## Project Layout

```
wavern/
  audio/           — place audio files here (default import directory)
  video/           — exported videos land here (default export directory)
  src/wavern/      — main package
  tests/           — pytest test suite
  plugins/         — plugin development guide
```

## Development

```bash
uv sync --all-extras      # install dev dependencies
uv run pytest tests/ -v   # run tests
uv run ruff check src/    # lint
```

## License

[GPL-3.0](LICENSE)

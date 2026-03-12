# Contributing to Wavern

Thank you for your interest in contributing. This document covers everything you need to get started.

## Getting Started

1. Fork the repository and clone your fork:
   ```bash
   git clone https://github.com/Lorakszak/wavern.git
   cd wavern
   ```
2. Install all dependencies including dev extras:
   ```bash
   uv sync --all-extras
   ```
3. Verify the test suite passes before making any changes:
   ```bash
   uv run pytest tests/ -v
   ```

## Development Workflow

### Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-description>` | `feat/plasma-visualization` |
| Bug fix | `fix/<short-description>` | `fix/export-alpha-channel` |
| Docs | `docs/<short-description>` | `docs/preset-format` |
| Refactor | `refactor/<short-description>` | `refactor/renderer-pipeline` |

### Commit conventions

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add plasma visualization type
fix: correct VP9 alpha channel handling in headless export
refactor: extract uniform upload helpers to base class
docs: document preset JSON schema fields
test: add coverage for circular spectrum beat sync
```

Never force-push to `main`. All changes go through pull requests.

## Testing

```bash
uv run pytest tests/ -v          # full suite
uv run pytest tests/ -v -k foo   # run tests matching "foo"
```

The suite must stay at **27 passing tests**. New visualizations and features require corresponding tests. Do not mock internal subsystems (renderer, audio analyzer) — use real objects.

## Linting

```bash
uv run ruff check src/          # lint
uv run ruff check src/ --fix    # auto-fix safe issues
```

Line length is **100 characters** (configured in `pyproject.toml`). All function signatures must have type hints. Use Google-style docstrings.

## Adding a Visualization

1. Create `src/wavern/visualizations/my_viz.py` and subclass `AbstractVisualization`
2. Set class attributes: `NAME`, `DISPLAY_NAME`, `DESCRIPTION`, `CATEGORY`, `PARAM_SCHEMA`
3. Implement `initialize()`, `render()`, `cleanup()`:
   - GPU resources (shaders, buffers, textures) go in `initialize()`, not `__init__`
   - Use `self._set_uniform(prog, name, value)` / `self._write_uniform(prog, name, data)` for all
     uniforms — never `prog[name].value = ...` directly (strips optimised-out uniforms raise `KeyError`)
   - `render()` receives a `FrameAnalysis` dataclass — never raw audio
4. Apply the `@register` decorator to the class
5. Add the import to `src/wavern/visualizations/__init__.py`
6. Create a matching preset JSON in `src/wavern/presets/defaults/`

See `src/wavern/visualizations/spectrum_bars.py` as a reference implementation.

## Submitting a Pull Request

1. Ensure all 27 tests pass: `uv run pytest tests/ -v`
2. Ensure ruff is clean: `uv run ruff check src/`
3. Fill out the [pull request template](.github/PULL_REQUEST_TEMPLATE.md)
4. Open the PR against `main`

## Reporting Bugs / Requesting Features

Use the GitHub issue templates:

- **Bug report** — [open a bug](https://github.com/Lorakszak/wavern/issues/new?template=bug_report.yml)
- **Feature request** — [open a feature request](https://github.com/Lorakszak/wavern/issues/new?template=feature_request.yml)

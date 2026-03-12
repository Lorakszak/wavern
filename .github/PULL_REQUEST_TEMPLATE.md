## Summary

<!-- What does this PR do? Why? 1–3 bullet points. -->

-

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] New visualization
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Tests
- [ ] Other (describe):

## Testing done

<!-- How did you test this? Which commands did you run? -->

```bash
uv run pytest tests/ -v
uv run ruff check src/
```

## Checklist

- [ ] All 27 tests pass (`uv run pytest tests/ -v`)
- [ ] `uv run ruff check src/` reports no issues
- [ ] New functions/methods have type hints on all parameters and return types
- [ ] New public functions/methods have Google-style docstrings
- [ ] If adding a visualization: preset JSON added to `src/wavern/presets/defaults/`
- [ ] If adding a visualization: import added to `src/wavern/visualizations/__init__.py`

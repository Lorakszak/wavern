Closes #

## Summary

<!-- What does this PR do? Why? 1-5 bullet points. -->

-

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] New visualization
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Tests
- [ ] Other (describe):

## Screenshots / Demo

<!-- For UI changes or new visualizations, attach a screenshot or short GIF.
     Not required for docs / refactor / test-only PRs. -->

## Breaking changes

<!-- Does this PR change any public API, preset schema, CLI flags, or visualization params?
     If yes, describe what breaks and what the migration path is. -->

None.

## Testing done

<!-- Describe what you manually verified. Which edge cases did you check? -->

Commands run:

```bash
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
```

## Checklist

- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] `uv run ruff check src/` reports no issues (or existing errors not increased)
- [ ] `uv run mypy src/` passes (or existing errors not increased)
- [ ] New tests added covering newly introduced functionality (if any)
- [ ] New functions/methods have type hints on all parameters and return types
- [ ] New public functions/methods have Google-style docstrings
- [ ] If adding/changing a visualization: preset JSON updated in `src/wavern/presets/defaults/`
- [ ] No unrelated changes included in this PR

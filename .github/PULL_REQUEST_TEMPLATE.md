## What

## Why

## How to verify

- [ ] `uv run ruff check . && uv run mypy && uv run pytest --cov`
- [ ] `uv run flaky-radar render samples/results --out site` and open `site/index.html`
- [ ] If `scripts/make_samples.py` changed: regenerate and commit `samples/`

## Checklist

- [ ] Scoring changes are explained in the README and reflected in the dashboard footer
- [ ] Reusable workflow inputs stay backwards compatible

# flaky-test-radar

[![CI](https://github.com/yassineaitt/flaky-test-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/yassineaitt/flaky-test-radar/actions/workflows/ci.yml)
[![Dashboard](https://img.shields.io/badge/sample%20dashboard-GitHub%20Pages-2ea44f?logo=github)](https://yassineaitt.github.io/flaky-test-radar/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776ab?logo=python&logoColor=white)](pyproject.toml)
[![Reusable workflow](https://img.shields.io/badge/GitHub%20Actions-reusable%20workflow-2088ff?logo=githubactions&logoColor=white)](.github/workflows/radar.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Finds the tests that lie to you. `flaky-test-radar` reads JUnit XML or Allure results from
many CI runs, separates **flaky** tests from **always-failing** ones, tracks pass-rate and
retry trends, and renders a dependency-free HTML dashboard. It ships as a Python CLI and as a
**reusable GitHub Actions workflow** any repository can call in one job.

Live sample: **https://yassineaitt.github.io/flaky-test-radar/** (12 synthetic runs with
planted behaviours, regenerated from `scripts/make_samples.py`).

## Use it from another repository

```yaml
jobs:
  tests:
    # ... your matrix; each job uploads its JUnit XML as an artifact named junit-<something>
    steps:
      - run: npx playwright test --reporter=junit   # or pytest --junitxml, etc.
      - uses: actions/upload-artifact@v7
        with: { name: junit-${{ matrix.browser }}, path: test-results/junit.xml }

  flaky-radar:
    needs: [tests]
    if: always()                       # analyse red runs too - that is where the signal is
    permissions: { contents: write, actions: read }
    uses: yassineaitt/flaky-test-radar/.github/workflows/radar.yml@main
    with:
      artifact-pattern: junit-*
      max-runs: 50
      max-flaky: 3                     # optional budget; omit to never fail the build
```

What the workflow does in the calling repository:

1. downloads the run's matching artifacts;
2. appends them to an orphan branch (`flaky-radar-history` by default) and prunes it to
   `max-runs`, so history survives without external storage;
3. renders the dashboard, writes the Markdown summary to the **job summary**, uploads the
   site as an artifact, and optionally deploys it to the caller's GitHub Pages
   (`publish-pages: true`, which additionally needs `pages: write` and `id-token: write`
   on the calling job);
4. optionally **gates** the build on a flakiness budget and a minimum pass rate.

| Input              | Default               | Meaning                                                    |
| ------------------ | --------------------- | ---------------------------------------------------------- |
| `artifact-pattern` | `junit-*`             | Artifacts to collect from the calling run                  |
| `history-branch`   | `flaky-radar-history` | Where past runs are stored                                 |
| `max-runs`         | `50`                  | Window size for storage and analysis                       |
| `max-flaky`        | `-1`                  | Fail when more tests are flaky; `-1` disables the gate     |
| `min-pass-rate`    | `0`                   | Fail when the latest run's pass rate is below this (0-1)   |
| `publish-pages`    | `false`               | Deploy the dashboard to the caller's Pages                 |
| `radar-ref`        | `main`                | Pin a tag or SHA of this repository                        |

Output: `flaky-count`.

## Use it as a CLI

```bash
uv tool install git+https://github.com/yassineaitt/flaky-test-radar
flaky-radar analyze results/                 # ranked table
flaky-radar analyze results/ --json          # machine-readable
flaky-radar render  results/ --out site      # index.html + radar.json + summary.md
flaky-radar gate    results/ --max-flaky 3 --min-pass-rate 0.95   # exit 2 on breach
```

Input layout: one directory per run, named so it sorts chronologically (a `YYYY-MM-DDTHH-MM`
prefix is parsed as the run time), containing any number of JUnit `*.xml` and/or Allure
`*-result.json` files. Retries inside a run are detected automatically: several results for
the same test in one run collapse to the last attempt, and a fail-then-pass is recorded as a
**retry pass**.

## How flakiness is scored

A flaky test changes outcome without the code changing. Without commit data the radar uses
three observable signals and blends them for ranking:

| Signal                | Definition                                                          | Weight |
| --------------------- | ------------------------------------------------------------------- | ------ |
| retry pass            | failed, then passed, within the same run                            | 0.6 × retry-pass ratio |
| flip rate             | share of consecutive runs whose outcome differs                      | 0.5 × flip rate |
| intermittency         | 1 at a 50 % failure rate, 0 at 0 % or 100 %                          | 0.3 × intermittency |

`score = min(1, Σ)`. Verdicts: **flaky** ≥ 0.4, **suspicious** > 0, **always-failing** when
every counted run failed (a broken test or product, not a flaky one), otherwise **stable**.
Skipped runs are ignored. Each component is shown in the table so the number is explainable,
and the slowest tests by p95 get their own list because slowness is the usual root cause.

## Dashboard

- Headline tiles: flaky / suspicious / always-failing counts, latest pass rate and retry passes.
- Pass-rate bars per run with a retry-pass marker, as inline SVG.
- Ranked table with a per-test history strip (oldest → newest), fail rate, flips, retry
  passes, p95 duration and the last failure message.
- Single HTML file, no JavaScript, no CDN, light/dark aware. Safe to publish from a private
  repository's artifact or to GitHub Pages.

## Development

```bash
uv sync && uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
uv run pytest --cov            # 17 tests, ≥ 85 % gate (currently ~98 %)
uv run python scripts/make_samples.py   # regenerate samples/ (deterministic)
```

CI runs lint, types and tests, verifies the samples are reproducible, then **calls the
reusable workflow on itself** (`radar-self-test`) so a regression in `radar.yml` fails this
repository first, and publishes the sample dashboard to Pages.

## Project layout

```
src/flaky_radar/
├── models.py        TestResult / Run
├── parse.py         JUnit XML + Allure readers, run discovery
├── analyze.py       histories, score, verdicts, run summaries
├── report.py        HTML (Jinja2 template), JSON, Markdown
└── cli.py           analyze · render · gate
.github/workflows/radar.yml   reusable workflow
samples/results/              12 synthetic runs (see scripts/make_samples.py)
```

## License

[MIT](LICENSE) © Yassine Ait Tamarmoucht

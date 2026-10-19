"""Command-line interface: analyze a results tree, render the dashboard, or gate a build."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from flaky_radar import __version__
from flaky_radar.analyze import Analysis, analyze
from flaky_radar.parse import ParseError, load_runs
from flaky_radar.report import to_json, to_markdown, write_site

app = typer.Typer(
    name="flaky-radar",
    help="Detect flaky tests across CI runs and render a dashboard.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)

ResultsArg = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=False, help="Directory with one sub-directory per run."),
]
MaxRunsOpt = Annotated[
    int | None, typer.Option("--max-runs", min=2, help="Only the N most recent runs.")
]


def _version(value: bool) -> None:
    if value:
        console.print(f"flaky-radar {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Detect flaky tests across CI runs and render a dashboard."""


def _load(results: Path, max_runs: int | None) -> Analysis:
    try:
        runs = load_runs(results)
    except ParseError as exc:
        err.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(1) from exc
    if not runs:
        err.print(f"[bold red]error:[/] no runs with results found under {results}")
        raise typer.Exit(1)
    return analyze(runs, max_runs=max_runs)


@app.command(name="analyze")
def analyze_cmd(
    results: ResultsArg,
    max_runs: MaxRunsOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of a table.")] = False,
    as_markdown: Annotated[
        bool, typer.Option("--markdown", help="Print a Markdown summary.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, help="Rows to show.")] = 25,
) -> None:
    """Rank tests by flakiness and print the result."""
    analysis = _load(results, max_runs)
    if as_json:
        sys.stdout.write(to_json(analysis) + "\n")
        return
    if as_markdown:
        sys.stdout.write(to_markdown(analysis, limit=limit))
        return
    table = Table(title=f"{len(analysis.runs)} runs · {len(analysis.tests)} tests")
    for col, just in (
        ("test", "left"),
        ("verdict", "left"),
        ("score", "right"),
        ("fail %", "right"),
        ("flips", "right"),
        ("retry passes", "right"),
    ):
        table.add_column(col, justify=just)  # type: ignore[arg-type]
    for t in analysis.tests[:limit]:
        table.add_row(
            t.test_id,
            t.verdict,
            f"{t.score:.2f}",
            f"{t.fail_rate:.0%}",
            str(t.flips),
            str(t.retry_passes),
        )
    console.print(table)


@app.command()
def render(
    results: ResultsArg,
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Output directory for the static site.")
    ] = Path("site"),
    max_runs: MaxRunsOpt = None,
    source: Annotated[
        str, typer.Option("--source", help="Label shown in the header (repo, branch…).")
    ] = "",
) -> None:
    """Write index.html, radar.json and summary.md for publishing (e.g. GitHub Pages)."""
    analysis = _load(results, max_runs)
    written = write_site(analysis, out, source=source)
    for p in written:
        console.print(f"[green]wrote[/] {p}")
    console.print(
        f"{len(analysis.flaky)} flaky · {len(analysis.suspicious)} suspicious · "
        f"{len(analysis.always_failing)} always failing"
    )


@app.command()
def gate(
    results: ResultsArg,
    max_runs: MaxRunsOpt = None,
    max_flaky: Annotated[
        int, typer.Option("--max-flaky", min=0, help="Fail when more tests are flaky.")
    ] = 0,
    min_pass_rate: Annotated[
        float,
        typer.Option(
            "--min-pass-rate", min=0.0, max=1.0, help="Fail when the latest run is below this."
        ),
    ] = 0.0,
) -> None:
    """Exit non-zero when the flakiness budget is exceeded (use in CI)."""
    analysis = _load(results, max_runs)
    latest = analysis.runs[-1]
    problems: list[str] = []
    if len(analysis.flaky) > max_flaky:
        problems.append(f"{len(analysis.flaky)} flaky tests > budget {max_flaky}")
    if latest.pass_rate < min_pass_rate:
        problems.append(f"latest pass rate {latest.pass_rate:.1%} < {min_pass_rate:.1%}")
    sys.stdout.write(to_markdown(analysis))
    if problems:
        err.print("[bold red]gate failed:[/] " + "; ".join(problems))
        raise typer.Exit(2)
    console.print("[green]gate passed[/]")


def main() -> None:  # pragma: no cover
    app()

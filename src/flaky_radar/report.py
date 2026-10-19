"""Render the analysis as a self-contained HTML dashboard, JSON and a Markdown summary."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from flaky_radar.analyze import Analysis

_env = Environment(
    loader=PackageLoader("flaky_radar", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(analysis: Analysis, *, source: str = "", max_rows: int = 200) -> str:
    template = _env.get_template("dashboard.html.j2")
    return template.render(
        analysis=analysis,
        latest=analysis.runs[-1] if analysis.runs else None,
        generated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        source=source,
        max_rows=max_rows,
    )


def to_json(analysis: Analysis) -> str:
    payload = {
        "runs": [asdict(r) | {"pass_rate": round(r.pass_rate, 4)} for r in analysis.runs],
        "tests": [
            {
                "test_id": t.test_id,
                "suite": t.suite,
                "name": t.name,
                "verdict": t.verdict,
                "score": t.score,
                "runs": t.runs,
                "failures": t.failures,
                "fail_rate": round(t.fail_rate, 4),
                "flips": t.flips,
                "retry_passes": t.retry_passes,
                "p95_duration_s": round(t.p95_duration, 3),
                "outcomes": t.outcomes,
                "last_message": t.last_message,
            }
            for t in analysis.tests
        ],
    }
    return json.dumps(payload, indent=2)


def to_markdown(analysis: Analysis, *, limit: int = 15) -> str:
    latest = analysis.runs[-1] if analysis.runs else None
    lines = ["## Flaky Test Radar", ""]
    if latest:
        lines.append(
            f"Latest run `{latest.run_id}`: {latest.passed}/{latest.total - latest.skipped} passed "
            f"({latest.pass_rate:.1%}), {latest.retry_passes} retry pass(es). "
            f"Window: {len(analysis.runs)} runs, {len(analysis.tests)} tests."
        )
        lines.append("")
    lines.append(
        f"**{len(analysis.flaky)} flaky**, {len(analysis.suspicious)} suspicious, "
        f"{len(analysis.always_failing)} always failing."
    )
    ranked = [t for t in analysis.tests if t.verdict in ("flaky", "suspicious")][:limit]
    if ranked:
        lines += [
            "",
            "| test | verdict | score | fail rate | flips | retry passes |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for t in ranked:
            lines.append(
                f"| `{t.test_id}` | {t.verdict} | {t.score:.2f} | {t.fail_rate:.0%} "
                f"| {t.flips} | {t.retry_passes} |"
            )
    return "\n".join(lines) + "\n"


def write_site(analysis: Analysis, out_dir: Path, *, source: str = "") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "index.html": render_html(analysis, source=source),
        "radar.json": to_json(analysis),
        "summary.md": to_markdown(analysis),
    }
    written: list[Path] = []
    for name, content in files.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written

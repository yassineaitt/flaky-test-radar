import json
from pathlib import Path

from typer.testing import CliRunner

from flaky_radar.analyze import analyze
from flaky_radar.cli import app
from flaky_radar.parse import load_runs
from flaky_radar.report import render_html, to_json, to_markdown, write_site

runner = CliRunner()


def test_render_html_contains_key_sections(results_dir: Path) -> None:
    html = render_html(analyze(load_runs(results_dir)), source="unit")
    assert "<title>Flaky Test Radar</title>" in html
    assert "pkg.mod::t1" in html
    assert 'class="badge flaky"' in html
    assert "source <code>unit</code>" in html
    assert "<svg" in html


def test_json_and_markdown(results_dir: Path) -> None:
    analysis = analyze(load_runs(results_dir))
    data = json.loads(to_json(analysis))
    assert data["tests"][0]["test_id"] == "pkg.mod::t1"
    assert data["runs"][-1]["pass_rate"] == 0.5
    md = to_markdown(analysis)
    assert md.startswith("## Flaky Test Radar")
    assert "| `pkg.mod::t1` | flaky |" in md


def test_write_site(results_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    written = write_site(analyze(load_runs(results_dir)), out)
    assert sorted(p.name for p in written) == ["index.html", "radar.json", "summary.md"]


def test_cli_analyze_table_json_markdown(results_dir: Path) -> None:
    assert "flaky-radar 0.1.0" in runner.invoke(app, ["--version"]).output
    res = runner.invoke(app, ["analyze", str(results_dir)])
    assert res.exit_code == 0, res.output
    assert "always-failing" in res.output
    res = runner.invoke(app, ["analyze", str(results_dir), "--json"])
    assert json.loads(res.stdout)["tests"]
    res = runner.invoke(app, ["analyze", str(results_dir), "--markdown", "--max-runs", "2"])
    assert "Window: 2 runs" in res.stdout


def test_cli_render_and_gate(results_dir: Path, tmp_path: Path) -> None:
    res = runner.invoke(
        app, ["render", str(results_dir), "--out", str(tmp_path / "s"), "--source", "x"]
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / "s" / "index.html").exists()
    res = runner.invoke(app, ["gate", str(results_dir), "--max-flaky", "5"])
    assert res.exit_code == 0, res.output
    assert "gate passed" in res.output
    res = runner.invoke(
        app, ["gate", str(results_dir), "--max-flaky", "0", "--min-pass-rate", "0.9"]
    )
    assert res.exit_code == 2
    assert "flaky tests > budget" in res.output
    assert "pass rate" in res.output


def test_cli_errors(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    res = runner.invoke(app, ["analyze", str(empty)])
    assert res.exit_code == 1
    assert "no runs" in res.output
    bad = tmp_path / "bad" / "run-1"
    bad.mkdir(parents=True)
    (bad / "x.xml").write_text("<nope")
    assert runner.invoke(app, ["analyze", str(tmp_path / "bad")]).exit_code == 1

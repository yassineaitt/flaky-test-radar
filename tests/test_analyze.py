from pathlib import Path

from flaky_radar.analyze import analyze, final_status
from flaky_radar.models import TestResult as Result
from flaky_radar.parse import load_runs
from tests.conftest import SAMPLES


def _r(status: str) -> Result:
    return Result(
        run_id="r",
        run_at="2026-01-01T00:00:00+00:00",
        suite="s",
        name="n",
        status=status,
        duration_s=1,
    )  # type: ignore[arg-type]


def test_final_status_collapses_retries() -> None:
    assert final_status([_r("failed"), _r("passed")]) == ("passed", True)
    assert final_status([_r("passed")]) == ("passed", False)
    assert final_status([_r("failed"), _r("failed")]) == ("failed", False)


def test_verdicts_on_synthetic_history(results_dir: Path) -> None:
    analysis = analyze(load_runs(results_dir))
    by_id = {t.name: t for t in analysis.tests}
    assert by_id["t1"].verdict == "flaky"
    assert by_id["t1"].flips == 2
    assert by_id["t2"].retry_passes == 1
    assert by_id["t2"].verdict in ("flaky", "suspicious")
    assert by_id["t3"].verdict == "always-failing"
    assert by_id["t3"].score == 0.0
    assert by_id["t4"].verdict == "stable"
    assert by_id["t4"].p95_duration == 9.0
    assert analysis.tests[0].name == "t1"  # ranked first
    assert analysis.runs[0].retry_passes == 1
    assert analysis.runs[-1].pass_rate == 0.5


def test_window_limits_runs(results_dir: Path) -> None:
    analysis = analyze(load_runs(results_dir), max_runs=2)
    assert [r.run_id[-5:] for r in analysis.runs] == ["run-2", "run-3"]


def test_sample_dataset_detects_planted_behaviours() -> None:
    analysis = analyze(load_runs(SAMPLES))
    flaky = {t.test_id for t in analysis.flaky}
    assert "tests.ui.todo::persists_after_reload" in flaky  # alternates between runs
    assert "tests.ui.checkout::pays_with_card" in flaky  # passes only on retry
    assert {t.test_id for t in analysis.always_failing} == {"tests.api.booking::list_filter"}
    assert analysis.slowest[0].test_id == "tests.ui.checkout::shows_order_summary"
    assert all(
        t.verdict == "stable"
        for t in analysis.tests
        if t.test_id not in flaky | {"tests.api.booking::list_filter"}
    )

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from flaky_radar.parse import ParseError, load_runs, parse_allure_result, parse_junit, run_timestamp
from tests.conftest import SAMPLES, case, junit


def test_load_runs_sorts_chronologically_and_parses_timestamps(results_dir: Path) -> None:
    runs = load_runs(results_dir)
    assert [r.run_id[-5:] for r in runs] == ["run-1", "run-2", "run-3"]
    assert runs[0].run_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert runs[0].counts == {"passed": 2, "failed": 3, "skipped": 0, "broken": 0}


def test_junit_statuses_and_messages(tmp_path: Path, now: datetime) -> None:
    p = tmp_path / "j.xml"
    p.write_text(
        junit(
            case("a")
            + case("b", "failed", msg="AssertionError: x")
            + case("c", "error")
            + case("d", "skipped")
        )
    )
    results = parse_junit(p, run_id="r", run_at=now)
    assert [r.status for r in results] == ["passed", "failed", "broken", "skipped"]
    assert results[1].message == "AssertionError: x"
    assert results[0].test_id == "pkg.mod::a"
    assert results[0].source == "j.xml"


def test_junit_single_testsuite_root_and_bad_xml(tmp_path: Path, now: datetime) -> None:
    p = tmp_path / "single.xml"
    p.write_text('<testsuite name="only"><testcase name="x" time="nan-ish"/></testsuite>')
    (r,) = parse_junit(p, run_id="r", run_at=now)
    assert (r.suite, r.name, r.duration_s) == ("only", "x", 0.0)
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuite")
    with pytest.raises(ParseError, match="not valid XML"):
        parse_junit(bad, run_id="r", run_at=now)


def test_allure_result(tmp_path: Path, now: datetime) -> None:
    p = tmp_path / "abc-result.json"
    p.write_text(
        json.dumps(
            {
                "name": "login works",
                "fullName": "tests.login#test_login_works",
                "status": "broken",
                "statusDetails": {"message": "Timeout 30s"},
                "start": 1_700_000_000_000,
                "stop": 1_700_000_004_500,
                "labels": [{"name": "suite", "value": "auth"}],
            }
        )
    )
    (r,) = parse_allure_result(p, run_id="r", run_at=now)
    assert (r.suite, r.name, r.status, r.duration_s, r.message) == (
        "auth",
        "tests.login#test_login_works",
        "broken",
        4.5,
        "Timeout 30s",
    )
    bad = tmp_path / "x-result.json"
    bad.write_text("{")
    with pytest.raises(ParseError, match="not valid JSON"):
        parse_allure_result(bad, run_id="r", run_at=now)


def test_run_dir_mixes_formats_and_timestamp_fallback(tmp_path: Path) -> None:
    d = tmp_path / "run-without-timestamp"
    d.mkdir()
    (d / "a.xml").write_text(junit(case("x")))
    (d / "b-result.json").write_text(json.dumps({"name": "y", "status": "passed"}))
    runs = load_runs(tmp_path)
    assert len(runs) == 1
    assert {r.name for r in runs[0].results} == {"x", "y"}
    assert run_timestamp(d).tzinfo is not None


def test_load_runs_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        load_runs(tmp_path / "nope")


def test_samples_are_loadable() -> None:
    runs = load_runs(SAMPLES)
    assert len(runs) == 12
    assert all(r.results for r in runs)

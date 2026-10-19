from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

SAMPLES = Path(__file__).parents[1] / "samples" / "results"


def junit(cases: str, suite: str = "s") -> str:
    return (
        '<?xml version="1.0"?><testsuites>'
        f'<testsuite name="{suite}">{cases}</testsuite></testsuites>'
    )


def case(
    name: str, status: str = "passed", cls: str = "pkg.mod", t: float = 0.5, msg: str = "boom"
) -> str:
    inner = {
        "passed": "",
        "failed": f'<failure message="{msg}">trace</failure>',
        "error": f'<error message="{msg}"/>',
        "skipped": "<skipped/>",
    }[status]
    return f'<testcase classname="{cls}" name="{name}" time="{t}">{inner}</testcase>'


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    """Three runs: t1 alternates, t2 retry-passes once, t3 always fails, t4 stable."""
    runs = {
        "2026-10-01T09-00_run-1": [
            case("t1", "failed"),
            case("t2", "failed"),
            case("t2", "passed"),
            case("t3", "failed"),
            case("t4"),
        ],
        "2026-10-02T09-00_run-2": [case("t1"), case("t2"), case("t3", "error"), case("t4", t=9.0)],
        "2026-10-03T09-00_run-3": [
            case("t1", "failed"),
            case("t2"),
            case("t3", "failed"),
            case("t4"),
        ],
    }
    for name, cases in runs.items():
        d = tmp_path / name
        d.mkdir()
        (d / "junit.xml").write_text(junit("".join(cases)), encoding="utf-8")
    return tmp_path


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 1, tzinfo=UTC)

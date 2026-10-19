"""Readers for JUnit XML and Allure result files.

Layout expected on disk: one directory per CI run, named so that it sorts
chronologically, each holding any number of ``*.xml`` (JUnit) and/or
``*-result.json`` (Allure) files::

    results/
      2026-10-01T09-12_run-1001/junit-chromium-1.xml
      2026-10-01T09-12_run-1001/junit-chromium-2.xml
      2026-10-02T09-30_run-1002/...

The run id is the directory name; the timestamp is parsed from its prefix when present,
otherwise taken from the files' mtime.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from flaky_radar.models import Run, Status, TestResult

_TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})[T_ ](\d{2})[-:](\d{2})")


class ParseError(ValueError):
    pass


def run_timestamp(run_dir: Path) -> datetime:
    m = _TS_PREFIX.match(run_dir.name)
    if m:
        return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00+00:00")
    return datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)


def load_runs(root: Path) -> list[Run]:
    """Load every run directory under ``root`` in chronological order."""
    if not root.is_dir():
        msg = f"{root} is not a directory"
        raise ParseError(msg)
    runs: list[Run] = []
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        results = load_run_dir(run_dir)
        if results:
            runs.append(Run(run_id=run_dir.name, run_at=run_timestamp(run_dir), results=results))
    runs.sort(key=lambda r: (r.run_at, r.run_id))
    return runs


def load_run_dir(run_dir: Path) -> list[TestResult]:
    run_id = run_dir.name
    run_at = run_timestamp(run_dir)
    results: list[TestResult] = []
    for path in sorted(run_dir.rglob("*")):
        if path.suffix.lower() == ".xml":
            results.extend(parse_junit(path, run_id=run_id, run_at=run_at))
        elif path.name.endswith("-result.json"):
            results.extend(parse_allure_result(path, run_id=run_id, run_at=run_at))
    return results


# ---- JUnit ----------------------------------------------------------------------


def parse_junit(path: Path, *, run_id: str, run_at: datetime) -> list[TestResult]:
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - trusted CI artifacts, no external entities
    except ET.ParseError as exc:
        msg = f"{path}: not valid XML ({exc})"
        raise ParseError(msg) from exc
    out: list[TestResult] = []
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        suite_name = suite.get("name") or path.stem
        for case in suite.iter("testcase"):
            status: Status = "passed"
            message = ""
            if (node := case.find("failure")) is not None:
                status, message = "failed", _msg(node)
            elif (node := case.find("error")) is not None:
                status, message = "broken", _msg(node)
            elif case.find("skipped") is not None:
                status = "skipped"
            out.append(
                TestResult(
                    run_id=run_id,
                    run_at=run_at,
                    suite=case.get("classname") or suite_name,
                    name=case.get("name") or "<unnamed>",
                    status=status,
                    duration_s=_float(case.get("time")),
                    message=message,
                    source=path.name,
                )
            )
    return out


# ---- Allure ---------------------------------------------------------------------

_ALLURE_STATUS: dict[str, Status] = {
    "passed": "passed",
    "failed": "failed",
    "broken": "broken",
    "skipped": "skipped",
    "unknown": "broken",
}


def parse_allure_result(path: Path, *, run_id: str, run_at: datetime) -> list[TestResult]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"{path}: not valid JSON ({exc})"
        raise ParseError(msg) from exc
    labels = {lbl.get("name"): lbl.get("value") for lbl in data.get("labels", [])}
    suite = labels.get("suite") or labels.get("parentSuite") or labels.get("feature") or ""
    start, stop = data.get("start"), data.get("stop")
    duration = 0.0
    if isinstance(start, int) and isinstance(stop, int):
        duration = max(0.0, (stop - start) / 1000)
    details = data.get("statusDetails") or {}
    return [
        TestResult(
            run_id=run_id,
            run_at=run_at,
            suite=str(suite),
            name=str(data.get("fullName") or data.get("name") or "<unnamed>"),
            status=_ALLURE_STATUS.get(str(data.get("status", "unknown")), "broken"),
            duration_s=duration,
            message=str(details.get("message") or "")[:500],
            source=path.name,
        )
    ]


def _msg(node: ET.Element) -> str:
    text = node.get("message") or ""
    if not text:
        lines = (node.text or "").strip().splitlines()
        text = lines[0] if lines else ""
    return text[:500]


def _float(value: str | None) -> float:
    try:
        return max(0.0, float(value or 0))
    except ValueError:
        return 0.0

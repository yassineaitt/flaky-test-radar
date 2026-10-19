"""Generate deterministic sample CI history under samples/ (12 runs, 2 shards each).

The data encodes known behaviours so the dashboard has something honest to show:
- one test that fails on retry then passes (classic flaky),
- one that alternates between runs,
- one that always fails,
- a slow-but-stable test,
- the rest stable.
Run: uv run python scripts/make_samples.py
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1] / "samples" / "results"
rng = random.Random(42)

TESTS = {
    "tests.ui.todo": [
        "creates_a_todo",
        "marks_completed",
        "deletes_a_todo",
        "filters_active",
        "persists_after_reload",
    ],
    "tests.api.booking": ["create", "get_by_id", "update_put", "patch", "delete", "list_filter"],
    "tests.ui.checkout": ["applies_coupon", "pays_with_card", "shows_order_summary"],
}
FLAKY_RETRY = ("tests.ui.checkout", "pays_with_card")  # fails first attempt, passes on retry
FLAKY_ALTERNATE = ("tests.ui.todo", "persists_after_reload")  # flips between runs
ALWAYS_FAILING = ("tests.api.booking", "list_filter")
SLOW = ("tests.ui.checkout", "shows_order_summary")


def case_xml(cls: str, name: str, status: str, t: float, msg: str = "") -> str:
    inner = ""
    if status == "failed":
        inner = f'<failure message="{escape(msg)}">{escape(msg)}\n  at {cls}.{name}</failure>'
    elif status == "error":
        inner = f'<error message="{escape(msg)}">{escape(msg)}</error>'
    elif status == "skipped":
        inner = "<skipped/>"
    return f'    <testcase classname="{cls}" name="{name}" time="{t:.3f}">{inner}</testcase>'


def main() -> None:
    start = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
    for i in range(12):
        when = start + timedelta(days=i, minutes=rng.randint(0, 50))
        run_dir = ROOT / f"{when.strftime('%Y-%m-%dT%H-%M')}_run-{1001 + i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        shards: dict[str, list[str]] = {"junit-shard-1.xml": [], "junit-shard-2.xml": []}
        for cls, names in TESTS.items():
            for name in names:
                shard = (
                    shards["junit-shard-1.xml"]
                    if cls.startswith("tests.ui")
                    else shards["junit-shard-2.xml"]
                )
                base = rng.uniform(0.3, 2.5)
                key = (cls, name)
                if key == SLOW:
                    base = rng.uniform(8, 14)
                if key == ALWAYS_FAILING:
                    shard.append(
                        case_xml(cls, name, "failed", base, "AssertionError: expected 200, got 500")
                    )
                elif key == FLAKY_RETRY and i % 3 != 1:
                    shard.append(
                        case_xml(
                            cls,
                            name,
                            "failed",
                            base * 3,
                            "TimeoutError: waiting for locator('#pay')",
                        )
                    )
                    shard.append(case_xml(cls, name, "passed", base))  # retry
                elif key == FLAKY_ALTERNATE and i % 2 == 0:
                    shard.append(
                        case_xml(cls, name, "failed", base, "Expected 3 items, received 0")
                    )
                elif rng.random() < 0.02:
                    shard.append(case_xml(cls, name, "skipped", 0.0))
                else:
                    shard.append(case_xml(cls, name, "passed", base))
        for file, cases in shards.items():
            body = "\n".join(cases)
            xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n'
                f'  <testsuite name="{file[:-4]}" tests="{len(cases)}">\n{body}\n'
                "  </testsuite>\n</testsuites>\n"
            )
            (run_dir / file).write_text(xml, encoding="utf-8")
    print(f"wrote {len(list(ROOT.iterdir()))} runs under {ROOT}")


if __name__ == "__main__":
    main()

"""Turn raw results into flakiness signals and trends.

A test is *flaky* when it changes outcome without the code under test changing. Without
commit information we approximate that with three signals, each visible in the dashboard
so the reader can judge:

* **retry pass** - within one run the test failed and then passed (the strongest signal);
* **flip rate** - how often consecutive runs disagree (pass→fail or fail→pass);
* **intermittent failures** - a failure rate strictly between 0 and 1 across the window.

The score blends them into a single 0-1 number used only for ranking.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field

from flaky_radar.models import Run, Status, TestResult


@dataclass
class TestHistory:
    test_id: str
    suite: str
    name: str
    outcomes: list[tuple[str, Status]] = field(default_factory=list)  # (run_id, final status)
    retry_passes: int = 0
    durations: list[float] = field(default_factory=list)
    last_message: str = ""

    @property
    def runs(self) -> int:
        return len(self.outcomes)

    @property
    def failures(self) -> int:
        return sum(1 for _, s in self.outcomes if s in ("failed", "broken"))

    @property
    def fail_rate(self) -> float:
        counted = [s for _, s in self.outcomes if s != "skipped"]
        return self.failures / len(counted) if counted else 0.0

    @property
    def flips(self) -> int:
        seq = [s in ("failed", "broken") for _, s in self.outcomes if s != "skipped"]
        return sum(1 for a, b in itertools.pairwise(seq) if a != b)

    @property
    def flip_rate(self) -> float:
        n = len([s for _, s in self.outcomes if s != "skipped"])
        return self.flips / (n - 1) if n > 1 else 0.0

    @property
    def p95_duration(self) -> float:
        if not self.durations:
            return 0.0
        xs = sorted(self.durations)
        return xs[min(len(xs) - 1, round(0.95 * (len(xs) - 1)))]

    @property
    def score(self) -> float:
        """0 = stable, 1 = coin flip. Retry passes dominate; always-failing is not flaky."""
        if self.fail_rate in (0.0, 1.0) and self.retry_passes == 0:
            return 0.0
        intermittency = 1.0 - abs(0.5 - self.fail_rate) * 2  # peaks at 50 % failures
        retry = min(1.0, self.retry_passes / max(1, self.runs))
        return round(min(1.0, 0.5 * self.flip_rate + 0.3 * intermittency + 0.6 * retry), 3)

    @property
    def verdict(self) -> str:
        if self.score >= 0.4:
            return "flaky"
        if self.score > 0:
            return "suspicious"
        if self.fail_rate == 1.0:
            return "always-failing"
        return "stable"


@dataclass
class RunSummary:
    run_id: str
    run_at: str
    total: int
    passed: int
    failed: int
    skipped: int
    broken: int
    retry_passes: int
    duration_s: float

    @property
    def pass_rate(self) -> float:
        counted = self.total - self.skipped
        return self.passed / counted if counted else 0.0


@dataclass
class Analysis:
    runs: list[RunSummary]
    tests: list[TestHistory]  # sorted by score desc, then fail_rate desc

    @property
    def flaky(self) -> list[TestHistory]:
        return [t for t in self.tests if t.verdict == "flaky"]

    @property
    def suspicious(self) -> list[TestHistory]:
        return [t for t in self.tests if t.verdict == "suspicious"]

    @property
    def always_failing(self) -> list[TestHistory]:
        return [t for t in self.tests if t.verdict == "always-failing"]

    @property
    def slowest(self) -> list[TestHistory]:
        return sorted(self.tests, key=lambda t: -t.p95_duration)[:10]


def final_status(attempts: list[TestResult]) -> tuple[Status, bool]:
    """Collapse retries: the last attempt wins; report whether an earlier attempt failed."""
    statuses = [a.status for a in attempts]
    retried = any(s in ("failed", "broken") for s in statuses[:-1]) and statuses[-1] == "passed"
    return statuses[-1], retried


def analyze(runs: list[Run], *, max_runs: int | None = None) -> Analysis:
    window = runs[-max_runs:] if max_runs else runs
    histories: dict[str, TestHistory] = {}
    summaries: list[RunSummary] = []
    for run in window:
        grouped: dict[str, list[TestResult]] = defaultdict(list)
        for r in run.results:
            grouped[r.test_id].append(r)
        retry_passes = 0
        counts = {"passed": 0, "failed": 0, "skipped": 0, "broken": 0}
        for test_id, attempts in grouped.items():
            status, retried = final_status(attempts)
            counts[status] += 1
            retry_passes += int(retried)
            first = attempts[0]
            h = histories.setdefault(
                test_id, TestHistory(test_id=test_id, suite=first.suite, name=first.name)
            )
            h.outcomes.append((run.run_id, status))
            h.retry_passes += int(retried)
            h.durations.extend(a.duration_s for a in attempts)
            failed_msgs = [a.message for a in attempts if a.message]
            if failed_msgs:
                h.last_message = failed_msgs[-1]
        summaries.append(
            RunSummary(
                run_id=run.run_id,
                run_at=run.run_at.isoformat(timespec="minutes"),
                total=sum(counts.values()),
                retry_passes=retry_passes,
                duration_s=round(sum(r.duration_s for r in run.results), 1),
                **counts,
            )
        )
    tests = sorted(histories.values(), key=lambda t: (-t.score, -t.fail_rate, t.test_id))
    return Analysis(runs=summaries, tests=tests)

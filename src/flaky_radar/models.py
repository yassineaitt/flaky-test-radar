"""Normalised test results. Every input format (JUnit, Allure) is reduced to these."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["passed", "failed", "skipped", "broken"]


class TestResult(BaseModel):
    """One execution of one test in one run (retries produce several results)."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    run_at: datetime
    suite: str
    name: str
    status: Status
    duration_s: float = Field(ge=0)
    message: str = ""
    source: str = ""  # file the result came from, for traceability

    @property
    def test_id(self) -> str:
        return f"{self.suite}::{self.name}" if self.suite else self.name


class Run(BaseModel):
    run_id: str
    run_at: datetime
    results: list[TestResult]

    @property
    def counts(self) -> dict[str, int]:
        out = {"passed": 0, "failed": 0, "skipped": 0, "broken": 0}
        for r in self.results:
            out[r.status] += 1
        return out
